"""Internal tests only; real graph acceptance is recorded separately."""
import json
from pathlib import Path
import tempfile
import unittest
import threading
from types import SimpleNamespace

from laomedo.agent_activity import ActivityStore
from laomedo.agent_activity_projection import project
from laomedo.agent_activity_cost import estimate
from laomedo.runner_activity import notification, read_feed, closed_boundary


class GraphActivityTests(unittest.TestCase):
    def test_read_only_missing_store_does_not_create_anything(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'absent/activity.db'
            store=ActivityStore(path,read_only=True)
            with self.assertRaises(Exception):
                store.graph_runs('alice','flow')
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

    def test_durable_source_boundary_survives_late_resume(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'events.jsonl').write_text(''.join(json.dumps({'event':{'turn':turn}})+'\n' for turn in ['first','first','second']))
            (root/'activity-boundaries.jsonl').write_text(json.dumps({'native_start':0,'native_end':2})+'\n')
            bound=closed_boundary(root,0)
            page=read_feed(root/'events.jsonl',before=bound['native_end'])
            self.assertEqual([event['event']['turn'] for event in page['events']],['first','first'])
            self.assertEqual(page['next_after'],2)
            self.assertIsNone(closed_boundary(root,2))

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

    def test_frozen_boundary_excludes_downstream_resume(self):
        from laomedo.agent_activity_capture import RunnerCapture
        with tempfile.TemporaryDirectory() as directory:
            store=ActivityStore(Path(directory)/'activity.db')
            run=store.start('alice','flow','agent',execution='graph')
            capture=RunnerCapture.__new__(RunnerCapture)
            capture.capture=(store,run);capture.timeout=1;capture.after=0;capture.otel_after=0
            capture.boundary=(2,0);capture.boundary_status='completed';capture.boundary_time='2026-10-15T00:00:01Z'
            capture.component=SimpleNamespace(operation='fresh');capture.done=threading.Event();capture.done.set()
            events=[{'cursor':index,'received_at':'2026-10-15T00:00:00Z','event':{'method':method}}
                    for index,method in enumerate(('turn/started','turn/completed','turn/started'),1)]
            capture.feed=lambda _: {'events':events,'next_after':3,'status':'running','thread_id':'thread','model':'gpt-6-luna'}
            capture.observe('runner')
            page=store.read('alice','flow','agent',run)
            self.assertEqual(page['run']['status'],'completed')
            self.assertEqual(page['run']['ended'],'2026-10-15T00:00:01Z')
            self.assertEqual(len(page['events']),2)
