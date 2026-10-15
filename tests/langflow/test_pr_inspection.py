import unittest
from unittest.mock import patch
from fastapi import FastAPI, HTTPException, Header
from fastapi.testclient import TestClient
from pathlib import Path
from laomedo.langflow_skill_viewer import install_routes


class PRInspectionTests(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        def authenticate(authorization: str = Header(default='')):
            if authorization != 'Bearer dummy': raise HTTPException(401)
        install_routes(app, Path('/unused'), authenticate)
        self.client = TestClient(app)
        self.body = {'repository_url':'https://github.com/owner/repo','pr_number':1,'labels':[],'state':'open'}
        self.headers = {'Authorization':'Bearer dummy'}

    def test_authenticated_read_only_no_store(self):
        with patch('laomedo.github_pr_client.pr_request', return_value={'pr':{'number':1}, 'fetched_at':'now', 'operation':{'status':'not_requested'}}) as backend:
            self.assertEqual(self.client.post('/api/v1/laomedo/github-prs/inspect', json=self.body).status_code, 401)
            result = self.client.post('/api/v1/laomedo/github-prs/inspect', json=self.body, headers=self.headers)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['schema_version'], 'laomedo.pr-inspection.v1')
            self.assertEqual(result.headers['cache-control'], 'no-store')
            backend.assert_called_once_with('execute', **self.body, operation=None)

    def test_operation_and_invalid_identity_never_reach_gateway(self):
        with patch('laomedo.github_pr_client.pr_request') as backend:
            for body in ({**self.body,'operation':{'action':'close'}}, {**self.body,'pr_number':True},
                         {**self.body,'repository_url':'https://evil.invalid'}):
                self.assertEqual(self.client.post('/api/v1/laomedo/github-prs/inspect', json=body, headers=self.headers).status_code,400)
            backend.assert_not_called()

    def test_failed_read_omits_provider_details(self):
        with patch('laomedo.github_pr_client.pr_request', side_effect=RuntimeError('private-token')):
            response = self.client.post('/api/v1/laomedo/github-prs/inspect',json=self.body,headers=self.headers)
            self.assertEqual(response.status_code,400)
            self.assertNotIn('private-token',response.text)
