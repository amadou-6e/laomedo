import unittest
from laomedo.opencode_activity import project


def message(identity, role, text, **changes):
    return {'info':{'id':identity,'role':role,'sessionID':'ses_root','time':{'created':1000,'completed':2000},**changes},
            'parts':[{'type':'text','text':text}]}


def event(messages):
    return {'received_at':'2026-10-19T10:00:00+00:00','raw':{'method':'opencode/messageSnapshot','params':{'sessionID':'ses_root','messages':messages}}}


class OpenCodeActivityTests(unittest.TestCase):
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
