"""Dependency-light CI regressions; genuine graph acceptance is separate."""
import unittest
from laomedo.activity.agent_activity.projection import project


def event(method, **params):
    return {'raw':{'method':method,'params':params},'received_at':'2026-10-26T10:00:00Z'}


class CodexActivityParityTests(unittest.TestCase):
    def test_attested_fresh_boundary_prices_entire_first_turn_not_last_request(self):
        data=[{'raw':{'method':'capture/usageBaseline','threads':{},'fresh_thread':True},'received_at':'2026-10-26T10:00:00Z'},
              event('turn/started',threadId='root',turnId='turn')]
        for tokens in (100,170,170):
            data.append(event('thread/tokenUsage/updated',threadId='root',turnId='turn',
                tokenUsage={'total':{'inputTokens':tokens,'cachedInputTokens':20,'outputTokens':10},'last':{'inputTokens':7}}))
        result=project(data,root_thread='root',model='gpt-6-luna')
        self.assertEqual(result['turns'][0]['usage']['inputTokens'],170)
        self.assertEqual(result['usage']['inputTokens'],170)
        self.assertIsNotNone(result['turns'][0]['cost']['amount'])
        self.assertEqual([p['turn_usage']['inputTokens'] for p in result['usage_points']],[100,170,170])

    def test_missing_boundary_remains_unknown_for_resume_and_legacy_capture(self):
        for marker in ({},{'fresh_thread':False}):
            data=[{'raw':{'method':'capture/usageBaseline','threads':{},**marker},'received_at':'2026-10-26T10:00:00Z'},
                  event('turn/started',threadId='root',turnId='turn'),
                  event('thread/tokenUsage/updated',threadId='root',turnId='turn',tokenUsage={'total':{'inputTokens':100},'last':{'inputTokens':100}})]
            self.assertIsNone(project(data,root_thread='root')['turns'][0]['usage'])

    def test_streamed_message_and_command_are_provisional_completed_item_wins(self):
        data=[event('item/started',threadId='root',turnId='turn',item={'id':'msg','type':'agentMessage','text':''}),
              event('item/agentMessage/delta',threadId='root',turnId='turn',itemId='msg',delta='Hello'),
              event('item/started',threadId='root',turnId='turn',item={'id':'cmd','type':'commandExecution','aggregatedOutput':None}),
              event('item/commandExecution/outputDelta',threadId='root',turnId='turn',itemId='cmd',delta='line\n')]
        result=project(data,root_thread='root')
        self.assertEqual(result['items'][0]['item']['text'],'Hello')
        self.assertEqual(result['items'][1]['item']['aggregatedOutput'],'line\n')
        final=event('item/completed',threadId='root',turnId='turn',item={'id':'msg','type':'agentMessage','text':'Complete answer'})
        late=event('item/agentMessage/delta',threadId='root',turnId='turn',itemId='msg',delta='obsolete')
        self.assertEqual(project([*data,final,late],root_thread='root')['items'][0]['item']['text'],'Complete answer')
        self.assertEqual(data[0]['raw']['params']['item']['text'],'') # Native evidence is immutable.

    def test_child_source_parent_and_title_survive_spawn_tool_receipts(self):
        data=[event('thread/started',thread={'id':'child','source':{'subAgent':{'thread_spawn':{'parent_thread_id':'root'}}},'agentNickname':'Reader'}),
              event('item/completed',threadId='root',turnId='parent-turn',item={'id':'spawn','type':'collabAgentSpawnToolCall','agentThreadId':'child'}),
              event('turn/started',threadId='child',turnId='child-turn'),event('turn/failed',threadId='child',turnId='child-turn')]
        result=project(data,root_thread='root')
        self.assertEqual(result['threads'],[{'id':'child','parent':'root','title':'Reader'}])
        child=next(t for t in result['turns'] if t['thread']=='child')
        self.assertEqual(child['status'],'failed');self.assertIsNotNone(child['ended'])
        self.assertIsNone(result['usage']) # No independent child usage was captured.

    def test_explicit_otel_aliases_scope_but_conflicting_ids_do_not(self):
        records=[{'attributes':{'thread_id':'root','turn_id':'t','call_id':'c'}},
                 {'attributes':{'conversation.id':'other','thread_id':'root'}}]
        result=project([event('otel/record',**r) for r in records],root_thread='root')
        self.assertEqual(result['telemetry'][0]['attributes']['conversation.id'],'root')
        self.assertEqual(result['telemetry'][0]['attributes']['turn.id'],'t')
        self.assertEqual(result['telemetry'][1]['attributes']['conversation.id'],'other')
        self.assertTrue(result['telemetry'][1]['scope_conflict'])
        self.assertEqual(records[0]['attributes'],{'thread_id':'root','turn_id':'t','call_id':'c'})

    def test_native_child_creation_provides_first_boundary_without_replay_reset(self):
        spawn=event('item/started',threadId='root',turnId='t',item={'id':'spawn','type':'subAgentActivity','kind':'started','agentThreadId':'child','agentPath':'/root/reader'})
        data=[spawn,event('thread/started',thread={'id':'child','parentThreadId':'root'}),event('turn/started',threadId='child',turnId='child-turn'),
              event('thread/tokenUsage/updated',threadId='child',turnId='child-turn',tokenUsage={'total':{'inputTokens':100,'cachedInputTokens':0,'outputTokens':5}}),spawn,
              event('thread/tokenUsage/updated',threadId='child',turnId='child-turn',tokenUsage={'total':{'inputTokens':150,'cachedInputTokens':0,'outputTokens':6}})]
        result=project(data,root_thread='root')
        child=next(t for t in result['turns'] if t['thread']=='child')
        self.assertEqual(child['usage']['inputTokens'],150)
        self.assertEqual(result['threads'][0]['title'],'reader')

    def test_late_child_start_does_not_invent_missing_boundary(self):
        data=[event('turn/started',threadId='child',turnId='ct'),event('item/started',threadId='root',turnId='t',item={'id':'spawn','type':'subAgentActivity','kind':'started','agentThreadId':'child'}),event('thread/tokenUsage/updated',threadId='child',turnId='ct',tokenUsage={'total':{'inputTokens':30}})]
        child=next(t for t in project(data,root_thread='root')['turns'] if t['thread']=='child')
        self.assertIsNone(child['usage'])


if __name__=='__main__':unittest.main()
