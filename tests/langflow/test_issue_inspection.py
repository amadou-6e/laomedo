import unittest
from unittest.mock import patch
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pathlib import Path
from laomedo.langflow_skill_viewer import install_routes

class IssueInspectionTests(unittest.TestCase):
    def setUp(self):
        app=FastAPI()
        from fastapi import Header
        def authenticate(authorization: str = Header(default="")):
            if authorization != "Bearer dummy":raise HTTPException(401)
        install_routes(app,Path("/unused"),authenticate)
        self.client=TestClient(app)
        self.body={"repository_url":"https://github.com/owner/repo","issue_number":1,"labels":[],"state":"open"}
        self.headers={"Authorization":"Bearer dummy"}
    def test_inspection_is_authenticated_read_only_and_uncached(self):
        with patch("laomedo.github_issue_client.issue_request",return_value={"issue":{"number":1},"fetched_at":"now","operation":{"status":"not_requested"}}) as backend:
            self.assertEqual(self.client.post("/api/v1/laomedo/github-issues/inspect",json=self.body).status_code,401)
            response=self.client.post("/api/v1/laomedo/github-issues/inspect",json=self.body,headers=self.headers)
            self.assertEqual(response.status_code,200)
            self.assertEqual(response.json()["schema_version"],"laomedo.issue-inspection.v1")
            self.assertEqual(response.headers["cache-control"],"no-store")
            backend.assert_called_once_with("execute",**self.body,operation=None)
    def test_target_or_operation_override_is_refused_without_backend_call(self):
        with patch("laomedo.github_issue_client.issue_request") as backend:
            for payload in ({**self.body,"operation":{"action":"close"}}, {**self.body,"issue_number":True}, {**self.body,"repository_url":"https://evil.invalid"}):
                self.assertEqual(self.client.post("/api/v1/laomedo/github-issues/inspect",json=payload,headers=self.headers).status_code,400)
            backend.assert_not_called()
    def test_backend_failure_is_sanitized_and_never_becomes_content(self):
        with patch("laomedo.github_issue_client.issue_request",side_effect=RuntimeError("dummy-secret URL")):
            response=self.client.post("/api/v1/laomedo/github-issues/inspect",json=self.body,headers=self.headers)
            self.assertEqual(response.status_code,400)
            self.assertEqual(response.json(),{"detail":{"code":"github_issue_unavailable"}})
            self.assertNotIn("dummy-secret",response.text)
