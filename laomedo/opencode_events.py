"""Attempt-scoped native SSE receipts, with bounded capture and explicit gaps."""
import json
import re
import threading

from .runner_activity import receipt

ALLOWED = {'message.updated', 'message.part.updated', 'message.part.delta',
           'message.removed', 'message.part.removed', 'session.created',
           'session.updated', 'session.status', 'session.idle', 'session.error'}
SECRET_KEYS = {'authorization', 'password', 'api_key', 'apikey', 'access_token', 'refresh_token'}


def sanitized(value):
    if isinstance(value, dict):
        return {key: '[redacted]' if key.lower() in SECRET_KEYS else sanitized(item)
                for key, item in value.items()}
    if isinstance(value, list):
        return [sanitized(item) for item in value]
    if isinstance(value, str):
        return re.sub(r'(?i)Bearer\s+[A-Za-z0-9._~+/-]+', 'Bearer [redacted]', value)
    return value


def frames(response):
    """SSE data can span multiple lines; comments and heartbeats aren't actions."""
    data, size = [], 0
    while True:
        line = response.readline(1024 * 1024 + 1)
        if not line:
            return
        size += len(line)
        if size > 1024 * 1024:
            raise ValueError('opencode_sse_frame_size_limit')
        line = line.decode('utf-8').rstrip('\r\n')
        if not line:
            if data:
                yield json.loads('\n'.join(data))
            data, size = [], 0
        elif line.startswith('data:'):
            data.append(line[5:].lstrip(' '))


class NativeCapture:
    def __init__(self, root, session, baseline_ids=()):
        self.root, self.session = root, session
        self.baseline = set(baseline_ids)
        self.parents = {session: None}
        self.stop = threading.Event()
        self.ready = threading.Event()
        self.terminal = threading.Event()
        self.lock = threading.RLock()
        self.response = self.thread = None
        self.error = None
        self.busy = False
        self.saw_user = self.saw_assistant = False
        self.bytes = 0
        self.sealed = False
        self.child_idle = {}

    def append(self, event):
        raw = json.dumps(receipt(event), ensure_ascii=False) + '\n'
        with self.lock:
            if self.sealed:
                return
            self.bytes += len(raw.encode('utf8'))
            if self.bytes > 20 * 1024 * 1024 or len(raw.encode('utf8')) > 1024 * 1024:
                self.error = 'opencode_native_capture_size_limit'
                return
            with (self.root / 'activity-events.jsonl').open('a', encoding='utf8') as target:
                target.write(raw)

    def observe(self, native):
        if not isinstance(native, dict):
            return
        native = native.get('payload', native)
        if not isinstance(native, dict):
            return
        kind = native.get('type')
        if kind == 'server.connected':
            self.ready.set()
            return
        if kind not in ALLOWED:
            return
        props = native.get('properties') or {}
        if not isinstance(props, dict):
            return
        info = props.get('info') or {}
        part = props.get('part') or {}
        if not isinstance(info, dict) or not isinstance(part, dict):
            return
        if 'status' in props and not isinstance(props['status'], dict):
            return
        session = props.get('sessionID') or info.get('sessionID') or part.get('sessionID')
        with self.lock:
            if kind in {'session.created', 'session.updated'}:
                session = info.get('id', session)
                if info.get('parentID') in self.parents:
                    self.parents[session] = info['parentID']
            if session not in self.parents:
                return
            message_id = info.get('id') if kind == 'message.updated' else props.get('messageID') or part.get('messageID')
            if message_id in self.baseline:
                return
            if session != self.session:
                self.child_idle.setdefault(session, False)
                if kind == 'session.idle' or kind == 'session.status' and (props.get('status') or {}).get('type') == 'idle':
                    self.child_idle[session] = True
                elif kind == 'session.status' and (props.get('status') or {}).get('type') == 'busy':
                    self.child_idle[session] = False
            if session == self.session:
                if kind == 'session.status' and (props.get('status') or {}).get('type') == 'busy':
                    self.busy = True
                if kind == 'message.updated':
                    self.saw_user |= info.get('role') == 'user'
                    self.saw_assistant |= info.get('role') == 'assistant'
                if self.busy and (kind == 'session.idle' or kind == 'session.status' and
                                  (props.get('status') or {}).get('type') == 'idle'):
                    self.terminal.set()
            self.append({'method': 'opencode/event', 'params': {'sessionID': session,
                         'event': sanitized(native)}})

    def start(self, backend):
        try:
            self.response = backend.open_events()
            def read():
                try:
                    for event in frames(self.response):
                        if self.stop.is_set():
                            return
                        self.observe(event)
                    if not self.stop.is_set():
                        self.error = 'opencode_native_stream_ended_early'
                except Exception:
                    if not self.stop.is_set():
                        self.error = 'opencode_native_stream_interrupted'
                finally:
                    self.ready.set()
            self.thread = threading.Thread(target=read, name='opencode-native-events', daemon=True)
            self.thread.start()
            if not self.ready.wait(5):
                self.error = 'opencode_native_subscription_not_ready'
        except Exception:
            self.error = 'opencode_native_subscription_unavailable'

    def close(self):
        self.stop.set()
        with self.lock:
            self.sealed = True
        if self.response is not None:
            self.response.close()
        if self.thread:
            self.thread.join(5)
            if self.thread.is_alive():
                self.error = 'opencode_native_reader_cleanup_unverified'

    @property
    def complete(self):
        return not self.error and self.terminal.is_set() and self.saw_user and self.saw_assistant and all(self.child_idle.values())
