import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from laomedo.agent_inspection import inspect_run, list_runs
from laomedo.agent_inspection_client import inspection_request

RUN = '7433da21-1389-428a-b43b-75834fa57d99'


class AgentInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.directory = self.root / 'runs' / RUN
        self.directory.mkdir(parents=True)

    def record(self, **values):
        (self.directory / 'record.json').write_text(json.dumps({'run_id': RUN, **values}))

    def trace(self, events):
        (self.directory / 'raw-events.jsonl').write_text(''.join(json.dumps(e)+'\n' for e in events))

    def test_raw_content_is_withheld_and_unknown_usage_is_not_zero(self):
        self.record(status='completed', answer='{"task_outcome":"success","secret":"dummy-secret"}',
                    requested_model='gpt-6-luna', requested_effort='low',
                    output_validation={'contract_status':'rejected','errors':[{'code':'required','path':'/report','message':'dummy-secret'}]})
        self.trace([{'method':'item/completed','params':{'turnId':'turn-1','item':{
            'type':'commandExecution','id':'item-1','command':'dummy-secret',
            'aggregatedOutput':'dummy-secret','exitCode':1,'durationMs':40}}}])
        result = inspect_run(self.root, RUN)
        self.assertNotIn('dummy-secret', json.dumps(result))
        self.assertEqual(result['summary']['requested_model'], 'gpt-6-luna')
        self.assertIsNone(result['summary']['effective_model'])
        self.assertIsNone(result['summary']['usage']['input_tokens'])
        self.assertEqual(result['events'][0]['exit_code'], 1)

    def test_completed_execution_does_not_hide_invalid_final_json(self):
        self.record(status='completed', answer='{"task_outcome":"success"}}', evidence_complete=True)
        result = inspect_run(self.root, RUN)
        self.assertEqual(result['summary']['executor_status'], 'completed')
        self.assertEqual(result['summary']['task_outcome'], 'unknown')
        self.assertEqual(result['summary']['output_syntax']['reason'], 'extra_data')
        self.assertEqual(result['trace_status'], 'missing')

    def test_identity_and_cursor_are_checked(self):
        self.record(run_id='different')
        with self.assertRaisesRegex(ValueError,'identity_mismatch'):inspect_run(self.root,RUN)
        for selected in ('../auth.json', 'not-a-uuid'):
            with self.assertRaisesRegex(ValueError,'invalid_run_id'):inspect_run(self.root,selected)
        for cursor in (-1,True,1000001):
            with self.assertRaisesRegex(ValueError,'invalid_inspection_cursor'):inspect_run(self.root,RUN,cursor)

    def test_malformed_fields_remain_unknown(self):
        self.record(status=[], requested_effort={}, answer='{"task_outcome":[]}',
                    output_validation={'contract_status':[], 'errors':[{'code':[]} ]})
        self.trace([{'method':'turn/completed','params':{'turn':[],'item':{'type':[]}}}])
        result=inspect_run(self.root,RUN)
        self.assertEqual(result['summary']['executor_status'],'unknown')
        self.assertEqual(result['events'][0]['item_type'],'unknown')

    def test_pagination_preserves_sequence_and_malformed_tail(self):
        self.record()
        self.trace([{'method':'turn/started','params':{'turnId':'t'}} for _ in range(201)])
        first=inspect_run(self.root,RUN)
        second=inspect_run(self.root,RUN,first['next_cursor'])
        self.assertEqual(len(first['events']),200)
        self.assertEqual(second['events'][0]['sequence'],200)
        with (self.directory/'raw-events.jsonl').open('a') as stream:stream.write('{')
        self.assertEqual(inspect_run(self.root,RUN,200)['trace_status'],'invalid')

    def test_history_ignores_foreign_record_identity(self):
        self.record()
        self.assertEqual(list_runs(self.root)['runs'][0]['run_id'],RUN)
        self.record(run_id='foreign')
        self.assertEqual(list_runs(self.root)['runs'],[])

    def test_trace_size_limit_is_explicit(self):
        self.record()
        self.trace([{'method':'turn/started','params':{}}])
        with patch('laomedo.agent_inspection.MAX_TRACE',1):
            self.assertEqual(inspect_run(self.root,RUN)['trace_status'],'limited')

    def test_connection_refused_before_reading_transport_secret(self):
        with patch.dict('os.environ', {'LAOMEDO_AGENT_INSPECTION_URLS':'[]'}), patch('pathlib.Path.read_text') as read:
            with self.assertRaisesRegex(ValueError,'connection_unavailable'):
                inspection_request('http://127.0.0.1:8784',RUN)
            read.assert_not_called()

    def test_record_symlink_is_refused(self):
        outside=self.root/'outside.json'
        outside.write_text(json.dumps({'run_id':RUN}))
        try:(self.directory/'record.json').symlink_to(outside)
        except OSError:self.skipTest('OS does not permit unprivileged symlink creation')
        with self.assertRaisesRegex(ValueError,'path_denied'):inspect_run(self.root,RUN)
