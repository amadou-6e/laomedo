"""Internal tests only; real graph acceptance is recorded separately."""
import json
from pathlib import Path
import tempfile
import unittest
import threading
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

from laomedo.agent_activity import ActivityStore
from laomedo.agent_activity_projection import project
from laomedo.agent_activity_cost import estimate
from laomedo.runner_activity import notification, read_feed


class GraphActivityTests(unittest.TestCase):
    def test_concurrent_first_captures_serialize_schema_migration(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'activity.db'
            def start(index):
                return ActivityStore(path).start('alice','flow',f'node-{index}',execution='graph')
            with ThreadPoolExecutor(max_workers=8) as pool:
                runs=list(pool.map(start,range(8)))
            self.assertEqual(len(set(runs)),8)
            self.assertEqual(len(ActivityStore(path,read_only=True).graph_runs('alice','flow')),8)

    def test_read_only_missing_store_does_not_create_anything(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'absent/activity.db'
            with self.assertRaises(LookupError):
                ActivityStore(path,read_only=True)
            self.assertFalse(path.parent.exists())

    def test_execution_owner_scope_and_retry_deduplication(self):
        with tempfile.TemporaryDirectory() as directory:
            store=ActivityStore(Path(directory)/'activity.db')
            first=store.start('alice','flow','agent',execution='first')
            store.start('alice','flow','agent',execution='second')
            store.start('bob','flow','agent',execution='first')
            event={'method':'item/completed','params':{'item':{'id':'same'}}}
            for cursor in (1,1,2):
                store.append(first,event,source='native',cursor=cursor)
            runs=store.graph_runs('alice','flow','first')
            self.assertEqual([run['id'] for run in runs],[first])
            self.assertEqual(runs[0]['event_count'],2)
            readonly=ActivityStore(store.path,read_only=True)
            with self.assertRaises(Exception):readonly.start('alice','flow','agent')

    def test_feed_excludes_account_and_rpc_responses(self):
        for event in ({'id':1,'result':{'token':'private'}},{'method':'account/updated'}, {'method':'models/list'}):
            self.assertFalse(notification(event))
        self.assertTrue(notification({'method':'item/completed'}))

    def test_incomplete_feed_write_is_not_consumed(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'events.jsonl'
            path.write_bytes(b'{"event":{}}\n{"event":')
            self.assertEqual(read_feed(path)['next_after'],1)
            with path.open('ab') as output:output.write(b'{}}\n')
            self.assertEqual(read_feed(path,after=1)['events'][0]['cursor'],2)

    def test_counter_regression_is_unknown_even_after_positive_snapshot(self):
        events=[{'raw':{'method':'thread/tokenUsage/updated','params':{'threadId':'thread','tokenUsage':{'total':{
            'inputTokens':value,'cachedInputTokens':0,'outputTokens':1}}}},'received_at':'2026-10-15T00:00:00Z'} for value in [100,50,120]]
        result=project(events,root_thread='thread',model='gpt-6-luna')
        self.assertIsNone(result['usage'])
        self.assertIsNone(result['cost']['amount'])

    def test_resume_deltas_and_repeated_cumulative_updates(self):
        events=[{'method':'capture/usageBaseline','threads':{'thread':{'total':{'inputTokens':100,'cachedInputTokens':20,'outputTokens':10}}}}]
        for inputs,cached,outputs in [(130,30,15),(130,30,15),(150,40,20)]:
            events.append({'method':'thread/tokenUsage/updated','params':{'threadId':'thread','turnId':'turn','tokenUsage':{
                'total':{'inputTokens':inputs,'cachedInputTokens':cached,'outputTokens':outputs}}}})
        result=project([{'raw':raw,'received_at':'2026-10-15T00:00:00Z'} for raw in events],root_thread='thread',model='gpt-6-luna')
        self.assertEqual(result['usage']['inputTokens'],50)
        self.assertEqual(result['usage']['cachedInputTokens'],20)
        self.assertEqual(result['usage']['outputTokens'],10)
        self.assertAlmostEqual(result['cost']['amount'],.0000082)

    def test_unknown_cost_is_not_zero(self):
        self.assertIsNone(estimate('unknown',{'inputTokens':0,'cachedInputTokens':0,'outputTokens':0})['amount'])
        usage={'inputTokens':0,'cachedInputTokens':0,'outputTokens':0}
        self.assertEqual(estimate('gpt-6-luna',usage)['amount'],0)
        self.assertIsNone(estimate('gpt-6-luna',{**usage,'cacheWriteInputTokens':1})['amount'])
        self.assertIsNone(estimate('gpt-6-luna',{**usage,'inputTokens':300000})['amount'])

    def test_conflicting_native_item_ids_are_visible(self):
        events=[{'raw':{'method':'item/completed','params':{'threadId':'t','turnId':'turn','item':{'id':'i','text':text}}},'received_at':'2026-10-15T00:00:00Z'} for text in ('first','different')]
        self.assertTrue(project(events)['items'][0]['conflicting_receipts'])

    def test_resume_initial_usage_does_not_invent_previous_turn(self):
        raw={'method':'thread/tokenUsage/updated','params':{'threadId':'thread','turnId':'previous',
             'tokenUsage':{'total':{'inputTokens':10,'cachedInputTokens':0,'outputTokens':0}}}}
        self.assertEqual(project([{'raw':raw,'received_at':'2026-10-15T00:00:00Z'}])['turns'],[])

    def test_refused_attempt_cannot_adopt_another_resume(self):
        from laomedo.agent_activity_capture import RunnerCapture
        with tempfile.TemporaryDirectory() as directory:
            store=ActivityStore(Path(directory)/'activity.db')
            invocation=store.start('alice','flow','refused',execution='graph')
            capture=RunnerCapture.__new__(RunnerCapture)
            capture.capture=(store,invocation);capture.timeout=1;capture.accepted=False
            capture.attempt_id='22222222-2222-4222-8222-222222222222'
            capture.refused=threading.Event();capture.done=threading.Event();capture.done.set()
            capture.outcome='failed'
            capture.feed=lambda *args: {'accepted':False,'events':[{'event':{'method':'turn/completed'}}]}
            capture.observe('runner')
            page=store.read('alice','flow','refused',invocation)
            self.assertEqual(page['events'],[])
            self.assertEqual(page['run']['status'],'failed')
            self.assertEqual(page['run']['reason'],'dispatch_not_accepted')

    def test_accepted_attempt_baseline_and_boundary_are_authoritative(self):
        from laomedo.agent_activity_capture import RunnerCapture
        with tempfile.TemporaryDirectory() as directory:
            store=ActivityStore(Path(directory)/'activity.db')
            invocation=store.start('alice','flow','agent',execution='graph')
            capture=RunnerCapture.__new__(RunnerCapture)
            capture.capture=(store,invocation);capture.timeout=1;capture.accepted=False
            capture.attempt_id='11111111-1111-4111-8111-111111111111'
            capture.refused=threading.Event();capture.done=threading.Event();capture.outcome=None
            capture.feed=lambda *args: {'accepted':True,'attempt':{'id':capture.attempt_id,
                'native_start':10,'native_end':11,'otel_start':3,'otel_end':3,
                'usage_baseline':{},'status':'completed','ended_at':'2026-10-15T00:00:01Z'},
                'events':[{'cursor':11,'received_at':'2026-10-15T00:00:00Z','event':{'method':'turn/completed'}}],
                'next_after':11,'telemetry':{'events':[],'next_after':3},'thread_id':'thread','model':'gpt-6-luna'}
            capture.observe('runner')
            page=store.read('alice','flow','agent',invocation)
            self.assertEqual(page['run']['status'],'completed')
            self.assertEqual(page['run']['ended'],'2026-10-15T00:00:01Z')
            self.assertEqual(len(page['events']),2)  # baseline plus this attempt's terminal
            other=store.start('alice','flow','duplicate',execution='other')
            self.assertFalse(store.claim_attempt(other,'runner',capture.attempt_id))
