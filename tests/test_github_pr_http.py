"""HTTP boundary controls; uses only local sockets and no provider calls."""
import json
import threading
import unittest
from unittest.mock import Mock
from urllib import request,error
from laomedo.github_pr_server import server


class PRHTTPTests(unittest.TestCase):
    def setUp(self):
        self.gateway=Mock();self.token='internal-test-token-'+'x'*32
        self.service=server(self.gateway,self.token,port=0)
        thread=threading.Thread(target=self.service.serve_forever,daemon=True);thread.start()
        self.addCleanup(self.service.server_close);self.addCleanup(self.service.shutdown)
        self.base='http://127.0.0.1:'+str(self.service.server_port)
        self.body={'repository_url':'https://github.com/owner/repo','labels':[],'state':'open','pr_number':1,'operation':None}

    def post(self,body,token=None):
        req=request.Request(self.base+'/v1/github-prs/execute',data=json.dumps(body).encode(),
            headers={'Content-Type':'application/json','Authorization':'Bearer '+(self.token if token is None else token)})
        try:
            with request.urlopen(req,timeout=5) as r:return r.status,json.load(r)
        except error.HTTPError as e:return e.code,json.load(e)

    def test_bearer_refusal_never_calls_gateway(self):
        self.assertEqual(self.post(self.body,token='wrong')[0],401)
        self.gateway.execute.assert_not_called()

    def test_expected_digest_is_forwarded_for_write(self):
        body={**self.body,'operation':{'action':'close'},'expected':'sha256:'+'a'*64}
        self.gateway.execute.return_value={'operation':{'status':'succeeded'}}
        self.assertEqual(self.post(body)[0],200)
        self.gateway.execute.assert_called_once_with(**body)

    def test_known_refusal_is_failed_before_dispatch(self):
        self.gateway.execute.side_effect=ValueError('pr_changed_since_agent_read')
        status,body=self.post({**self.body,'operation':{'action':'close'}})
        self.assertEqual((status,body['error_category']),(400,'pr_changed_since_agent_read'))

    def test_unknown_write_error_is_uncertain_and_sanitized(self):
        self.gateway.execute.side_effect=RuntimeError('private-provider-response')
        status,body=self.post({**self.body,'operation':{'action':'close'}})
        self.assertEqual((status,body['error_category']),(503,'pr_write_unknown'))
        self.assertNotIn('private-provider-response',json.dumps(body))

    def test_invalid_keys_never_reach_gateway(self):
        self.assertEqual(self.post({**self.body,'unexpected':True})[0],400)
        self.gateway.execute.assert_not_called()

    def test_feedback_routes_require_bearer_and_preserve_private_ticket(self):
        body={'ticket':'a'*64,'operation':{'action':'close'}}
        self.gateway.apply_feedback.return_value={'operation':{'status':'succeeded'}}
        encoded=json.dumps(body).encode()
        for bearer,expected in (('wrong',401),(self.token,200)):
            req=request.Request(self.base+'/v1/github-prs/apply-feedback',data=encoded,
                headers={'Content-Type':'application/json','Authorization':'Bearer '+bearer})
            try:
                with request.urlopen(req) as response:status=response.status
            except error.HTTPError as exc:status=exc.code
            self.assertEqual(status,expected)
        self.gateway.apply_feedback.assert_called_once_with(**body)

    def test_feedback_unknown_error_is_not_reported_as_safe_failure(self):
        self.gateway.apply_feedback.side_effect=RuntimeError('private-provider-message')
        req=request.Request(self.base+'/v1/github-prs/apply-feedback',
            data=json.dumps({'ticket':'a'*64,'operation':{'action':'close'}}).encode(),
            headers={'Content-Type':'application/json','Authorization':'Bearer '+self.token})
        with self.assertRaises(error.HTTPError) as raised:request.urlopen(req)
        self.assertEqual(raised.exception.code,503)
        self.assertEqual(json.load(raised.exception)['error_category'],'pr_write_unknown')
