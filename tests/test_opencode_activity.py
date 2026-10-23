import unittest
from laomedo.opencode_activity import project
from laomedo.opencode_activity import estimate_native


def message(identity, role, text, **changes):
    return {'info':{'id':identity,'role':role,'sessionID':'ses_root','time':{'created':1000,'completed':2000},**changes},
            'parts':[{'type':'text','text':text}]}


def event(messages):
    return {'received_at':'2026-10-19T10:00:00+00:00','raw':{'method':'opencode/messageSnapshot','params':{'sessionID':'ses_root','messages':messages}}}


class OpenCodeActivityTests(unittest.TestCase):
    def test_live_parts_deltas_and_checkpoint_reconcile_without_double_charging(self):
        user=message('user','user','Read README')
        answer=message('answer','assistant','Hello',parentID='user',providerID='test',modelID='model',
                       tokens={'input':4,'output':3,'reasoning':2,'cache':{'read':10,'write':1}})
        def native(kind,**properties):
            return {'received_at':'2026-10-23T10:00:00+00:00','raw':{'method':'opencode/event','params':{'sessionID':'ses_root','event':{'type':kind,'properties':properties}}}}
        events=[native('message.updated',info=user['info']),native('message.updated',info=answer['info']),
                native('message.part.updated',part={'id':'p','messageID':'answer','sessionID':'ses_root','type':'text','text':'Hel'}),
                native('message.part.delta',messageID='answer',partID='p',field='text',delta='lo')]
        live=project(events,root_thread='ses_root',model='test/model')
        self.assertEqual(live['items'][-1]['item']['text'],'Hello')
        final=project(events+[event([user,answer])],root_thread='ses_root',model='test/model')
        self.assertEqual(final['usage'],live['usage'])
        self.assertEqual(final['usage']['inputTokens'],15)
        self.assertEqual(len(final['usage_points']),1)
        late=native('message.part.updated',part={'id':'p','messageID':'answer','sessionID':'ses_root','type':'text','text':'Old partial'})
        reconciled=project(events+[event([user,answer]),late],root_thread='ses_root',model='test/model')
        self.assertEqual(reconciled['items'][-1]['item']['text'],'Hello')

    def test_native_child_link_inclusive_usage_and_unpriced_child_unknown(self):
        root=message('root','assistant','Parent',parentID='u',tokens={'input':4,'output':3,'reasoning':2,'cache':{'read':10,'write':1}})
        child=message('child','assistant','Child',sessionID='ses_child',parentID='c',tokens={'input':2,'output':1,'reasoning':0,'cache':{'read':0,'write':0}})
        link={'received_at':'2026-10-23T10:00:00+00:00','raw':{'method':'opencode/sessionSnapshot','params':{'session':{'id':'ses_child','parentID':'ses_root'}}}}
        snapshot=event([child]);snapshot['raw']['params']['sessionID']='ses_child'
        value=project([event([root]),link,snapshot],root_thread='ses_root',model='test/model')
        self.assertEqual(value['usage']['inputTokens'],17)
        self.assertIn({'id':'ses_child','parent':'ses_root'},value['threads'])
        self.assertEqual(value['usage_by_thread']['ses_child']['outputTokens'],1)
        self.assertIsNone(value['cost']['amount'])

    def test_native_catalog_prices_cache_writes_and_request_context_tiers(self):
        rates={'input':1,'output':5,'cache':{'read':0.1,'write':1.25},
               'tiers':[{'tier':{'type':'context','size':100},'input':2,'output':10,'cache':{'read':0.2,'write':2.5}}]}
        usage={'inputTokens':50,'cachedInputTokens':10,'cacheWriteInputTokens':10,'outputTokens':5}
        result=estimate_native('test/model',usage,rates)
        self.assertAlmostEqual(result['amount'],(30+1+12.5+25)/1_000_000)
        high=estimate_native('test/model',{**usage,'inputTokens':150},rates)
        self.assertAlmostEqual(high['amount'],(260+2+25+50)/1_000_000)
        self.assertIn('not a Go subscription charge',result['basis'])
        self.assertIsNone(estimate_native('test/model',{**usage,'inputTokens':1},rates)['amount'])

    def test_native_messages_keep_roles_sources_and_latest_usage_once(self):
        user=message('user','user','Read README')
        answer=message('answer','assistant','Done',parentID='user',tokens={'input':4,'output':3,'reasoning':2,'cache':{'read':10,'write':1}},cost=0)
        value=project([event([user,answer]),event([user,answer])],root_thread='ses_root',model='opencode-go/gpt-6-luna')
        self.assertEqual([item['item']['type'] for item in value['items']],['userMessage','agentMessage'])
        self.assertEqual(value['items'][1]['item']['native'],answer)
        self.assertEqual(value['usage']['inputTokens'],15)
        self.assertEqual(value['usage']['outputTokens'],5)
        self.assertEqual(len(value['usage_points']),1)
        self.assertIsNone(value['cost']['amount'])
        self.assertIn('snapshot',value['telemetry_coverage'])

    def test_missing_usage_remains_unknown_and_foreign_session_messages_are_excluded(self):
        foreign=message('foreign','assistant','Unrelated',sessionID='ses_other')
        value=project([event([foreign,message('answer','assistant','Done',parentID='user')])],root_thread='ses_root')
        self.assertIsNone(value['usage'])
        self.assertEqual(len(value['items']),1)
        self.assertNotIn('Unrelated',str(value))

    def test_command_tool_is_readable_and_preserves_native_metadata(self):
        answer=message('answer','assistant','Done',parentID='user')
        tool={'id':'tool','type':'tool','tool':'laomedo_exec','callID':'call','state':{'status':'completed','input':{'command':'head -n 6 README.md'},'output':'Real read result','metadata':{'exit':0},'time':{'start':1100,'end':1800}}}
        answer['parts'].insert(0,tool)
        value=project([event([answer])],root_thread='ses_root')
        command=next(item['item'] for item in value['items'] if item['item']['type']=='commandExecution')
        self.assertEqual(command['command'],'head -n 6 README.md')
        self.assertEqual(command['native'],tool)
        self.assertEqual(command['exitCode'],0)

    def test_worker_result_envelope_is_readable_without_changing_source(self):
        answer=message('answer','assistant','Done',parentID='user')
        tool={'id':'tool','type':'tool','tool':'laomedo_exec','state':{'input':{'command':'head -n 6 README.md'},'output':'{"exit_code":0,"stdout":"README\\n","stderr":""}'}}
        answer['parts']=[tool]
        value=project([event([answer])],root_thread='ses_root')
        command=value['items'][0]['item']
        self.assertEqual(command['aggregatedOutput'],'README\n')
        self.assertEqual(command['exitCode'],0)
        self.assertEqual(command['native'],tool)
