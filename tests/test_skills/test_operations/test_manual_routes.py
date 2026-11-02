"""Authenticated app boundary, safe errors and exact manual payload forwarding."""

import unittest
from unittest.mock import patch


class ManualSkillRouteTests(unittest.TestCase):
    def setUp(self):
        from fastapi import FastAPI, Header, HTTPException
        from fastapi.testclient import TestClient
        from laomedo.integrations.langflow.skill_editing import (
            install_skill_editing_routes,
        )

        def authenticate(authorization: str = Header(default="")):
            if authorization != "Bearer internal-unit":
                raise HTTPException(401)

        self.app = FastAPI()
        install_skill_editing_routes(self.app, authenticate)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)
        self.headers = {"Authorization": "Bearer internal-unit"}

    def test_authentication_origin_and_action_admission_precede_service(self):
        with patch(
            "laomedo.integrations.langflow.skill_editing.skill_request"
        ) as service:
            self.assertEqual(
                self.client.post(
                    "/api/v1/laomedo/skills/manual/save", json={}
                ).status_code,
                401,
            )
            self.assertEqual(
                self.client.post(
                    "/api/v1/laomedo/skills/manual/save",
                    json={},
                    headers={**self.headers, "Origin": "https://untrusted.invalid"},
                ).status_code,
                403,
            )
            self.assertEqual(
                self.client.post(
                    "/api/v1/laomedo/skills/manual/prepare",
                    json={},
                    headers=self.headers,
                ).status_code,
                404,
            )
            service.assert_not_called()

    def test_exact_safe_payload_and_no_store_receipt(self):
        payload = {"skill_id": "unit", "revision_id": "sha256:unit"}
        with patch(
            "laomedo.integrations.langflow.skill_editing.skill_request",
            return_value={"can_edit": False},
        ) as service:
            response = self.client.post(
                "/api/v1/laomedo/skills/manual/editor",
                json=payload,
                headers={**self.headers, "Origin": "http://testserver"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")
            service.assert_called_once_with("editor", **payload)

    def test_unknown_failure_is_uncertain_and_never_echoes_private_exception(self):
        with patch(
            "laomedo.integrations.langflow.skill_editing.skill_request",
            side_effect=OSError("private source and bearer secret"),
        ):
            response = self.client.post(
                "/api/v1/laomedo/skills/manual/save", json={}, headers=self.headers
            )
        self.assertEqual(
            response.json(), {"detail": {"code": "skill_manual_unavailable"}}
        )
        self.assertNotIn("private", response.text)

    def test_same_origin_admits_an_app_root_path_without_trusting_another_origin(self):
        from fastapi.testclient import TestClient

        with (
            TestClient(self.app, root_path="/laomedo") as client,
            patch(
                "laomedo.integrations.langflow.skill_editing.skill_request",
                return_value={"can_edit": False},
            ),
        ):
            self.assertEqual(
                client.post(
                    "/api/v1/laomedo/skills/manual/editor",
                    json={},
                    headers={**self.headers, "Origin": "http://testserver"},
                ).status_code,
                200,
            )
            self.assertEqual(
                client.post(
                    "/api/v1/laomedo/skills/manual/editor",
                    json={},
                    headers={**self.headers, "Origin": "https://testserver"},
                ).status_code,
                403,
            )
