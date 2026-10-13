import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from laomedo.langflow_skill_viewer import install_routes


class AgentInspectionRouteTests(unittest.TestCase):
    def setUp(self):
        app=FastAPI()
        def authenticate(authorization: str = Header(default='')):
            if authorization != 'Bearer dummy':raise HTTPException(401)
        install_routes(app,Path('/unused'),authenticate)
        self.client=TestClient(app)
        self.headers={'Authorization':'Bearer dummy'}
        self.payload={'runner_url':'http://127.0.0.1:8784','run_id':'7433da21-1389-428a-b43b-75834fa57d99','after':0}

    def test_authentication_and_no_cache(self):
        with patch('laomedo.agent_inspection_client.inspection_request',return_value={'schema_version':'laomedo.agent-inspection.v1'}) as backend:
            self.assertEqual(self.client.post('/api/v1/laomedo/agents/inspect',json=self.payload).status_code,401)
            result=self.client.post('/api/v1/laomedo/agents/inspect',json=self.payload,headers=self.headers)
            self.assertEqual(result.status_code,200)
            self.assertEqual(result.headers['cache-control'],'no-store')
            backend.assert_called_once_with(self.payload['runner_url'],self.payload['run_id'],0)

    def test_extra_operation_refused_and_backend_error_sanitized(self):
        with patch('laomedo.agent_inspection_client.inspection_request') as backend:
            result=self.client.post('/api/v1/laomedo/agents/inspect',json={**self.payload,'operation':'start'},headers=self.headers)
            self.assertEqual(result.status_code,400)
            backend.assert_not_called()
        with patch('laomedo.agent_inspection_client.inspection_request',side_effect=RuntimeError('dummy-secret')):
            result=self.client.post('/api/v1/laomedo/agents/inspect',json=self.payload,headers=self.headers)
            self.assertEqual(result.json(),{'detail':{'code':'inspection_unavailable'}})

    def test_history_is_authenticated(self):
        with patch('laomedo.agent_inspection_client.inspection_request',return_value={'schema_version':'laomedo.agent-history.v1'}) as backend:
            self.assertEqual(self.client.post('/api/v1/laomedo/agents/history',json={'runner_url':'http://127.0.0.1:8784'}).status_code,401)
            self.assertEqual(self.client.post('/api/v1/laomedo/agents/history',json={'runner_url':'http://127.0.0.1:8784'},headers=self.headers).status_code,200)
            self.assertEqual(backend.call_count,1)
