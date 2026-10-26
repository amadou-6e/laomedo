"""Internal native-schema fixtures; real acceptance requires a live graph run."""
import io
import json
from pathlib import Path
import tempfile
import unittest

from laomedo.opencode_events import NativeCapture, frames
from laomedo.runner_activity import read_feed


class OpenCodeEventTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.capture = NativeCapture(self.root, 'ses_root', {'old'})

    def emit(self, kind, **props):
        self.capture.observe({'id': 'evt_test', 'type': kind, 'properties': props})

    def test_sse_comments_multiline_and_frame_bound(self):
        data = b': heartbeat\n\ndata: {"type":\ndata: "server.connected"}\n\n'
        self.assertEqual(list(frames(io.BytesIO(data))), [{'type': 'server.connected'}])
        with self.assertRaises(ValueError):
            list(frames(io.BytesIO(b'data: '+b'x'*(1024*1024)+b'\n\n')))

    def test_terminal_requires_busy_user_assistant_and_idle(self):
        self.emit('session.idle', sessionID='ses_root')
        self.assertFalse(self.capture.complete)
        self.emit('session.status', sessionID='ses_root', status={'type': 'busy'})
        for role in ('user', 'assistant'):
            self.emit('message.updated', sessionID='ses_root', info={'id': role, 'sessionID': 'ses_root', 'role': role})
        self.emit('session.idle', sessionID='ses_root')
        self.assertTrue(self.capture.complete)
        self.capture.error = 'interrupted'
        self.assertFalse(self.capture.complete)

    def test_foreign_sessions_baseline_and_auth_events_not_captured(self):
        self.emit('message.updated', sessionID='ses_other', info={'id': 'foreign'})
        self.emit('message.updated', sessionID='ses_root', info={'id': 'old'})
        self.emit('auth.updated', sessionID='ses_root', value='never retain')
        self.assertFalse((self.root / 'activity-events.jsonl').exists())

    def test_child_requires_native_parent_link_and_secrets_are_redacted(self):
        self.emit('session.created', sessionID='ses_child', info={'id': 'ses_child', 'parentID': 'ses_root'})
        self.emit('message.updated', sessionID='ses_child', info={'id': 'child', 'sessionID': 'ses_child', 'role': 'assistant', 'Authorization': 'secret'})
        self.assertEqual(self.capture.parents['ses_child'], 'ses_root')
        events = read_feed(self.root / 'activity-events.jsonl')['events']
        self.assertEqual(len(events), 2)
        self.assertNotIn('secret', json.dumps(events))

    def test_unsupported_backend_degrades_capture_without_throwing(self):
        self.capture.start(object())
        self.capture.close()
        self.assertEqual(self.capture.error, 'opencode_native_subscription_unavailable')

    def test_empty_stream_is_not_complete(self):
        class Backend:
            def open_events(self): return io.BytesIO(b'data: {"type":"server.connected"}\n\n')
        self.capture.start(Backend())
        self.capture.thread.join(2)
        self.capture.close()
        self.assertFalse(self.capture.complete)

    def test_checkpoints_and_sse_share_writer_and_seal(self):
        from concurrent.futures import ThreadPoolExecutor
        from laomedo.opencode_activity import retain_messages
        def snapshot(index):
            retain_messages(self.root, 'ses_root', [{'info': {'id': str(index)}, 'parts': [{'text': 'x'*100000}]}], writer=self.capture)
        def event(index):
            self.capture.append({'method':'test/event','params':{'text':'y'*100000,'index':index}})
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda index: snapshot(index) if index % 2 else event(index), range(40)))
        lines=(self.root/'activity-events.jsonl').read_text().splitlines()
        self.assertEqual(len(lines),40)
        for line in lines: self.assertIsInstance(json.loads(line),dict)
        self.capture.close()
        snapshot(99)
        self.assertEqual((self.root/'activity-events.jsonl').read_text().splitlines(),lines)

    def test_malformed_native_records_are_ignored(self):
        for value in ({'payload':[]},{'type':'message.updated','properties':[]},
                      {'type':'message.updated','properties':{'info':42}}):
            self.capture.observe(value)
        self.assertFalse(self.capture.complete)

    def test_child_terminal_required_for_complete_capture(self):
        self.emit('session.status',sessionID='ses_root',status={'type':'busy'})
        self.emit('message.updated',sessionID='ses_root',info={'id':'u','role':'user'})
        self.emit('message.updated',sessionID='ses_root',info={'id':'a','role':'assistant'})
        self.emit('session.created',info={'id':'child','parentID':'ses_root'})
        self.emit('session.idle',sessionID='ses_root')
        self.assertFalse(self.capture.complete)
        self.emit('session.idle',sessionID='child')
        self.assertTrue(self.capture.complete)
