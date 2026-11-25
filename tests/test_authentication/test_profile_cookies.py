"""Current per-preview auth-cookie isolation; no credentials or native sign-in."""

import unittest
from importlib.util import find_spec

if find_spec("fastapi") is None:
    raise unittest.SkipTest("Optional FastAPI profile runtime is not installed")

from fastapi import FastAPI, Request, Response, WebSocket
from fastapi.testclient import TestClient

from laomedo.integrations.langflow.local_profiles.cookies import ProfileCookieBoundary


class ProfileCookieTests(unittest.TestCase):
    """Use real ASGI HTTP and WebSocket paths through the cookie boundary."""

    def setUp(self):
        self.app = FastAPI()
        self.app.add_api_route("/read", self.read)
        self.app.add_api_route("/private", self.private)
        self.app.add_api_route("/login", self.login, methods=["POST"])
        self.app.add_api_route("/logout", self.logout, methods=["POST"])
        self.app.add_api_websocket_route("/socket", self.socket)
        self.app.add_middleware(ProfileCookieBoundary, port=17884)
        self.client = TestClient(self.app)
        self.addCleanup(self.client.close)

    async def read(self, request: Request):
        return {
            "selected": request.cookies.get("access_token_lf") == "selected",
            "refresh": request.cookies.get("refresh_token_lf") == "refresh",
            "unrelated": request.cookies.get("theme"),
        }

    async def login(self):
        response = Response()
        response.set_cookie(
            "access_token_lf",
            "selected",
            httponly=True,
            secure=True,
            samesite="strict",
            max_age=90,
            path="/",
        )
        response.set_cookie(
            "refresh_token_lf", "refresh", httponly=True, samesite="lax"
        )
        response.set_cookie("theme", "dark")
        return response

    async def logout(self):
        response = Response()
        response.delete_cookie("access_token_lf", httponly=True)
        response.delete_cookie("refresh_token_lf", httponly=True)
        return response

    async def socket(self, websocket: WebSocket):
        await websocket.accept()
        await websocket.send_json(
            {"selected": websocket.cookies.get("access_token_lf") == "selected"}
        )
        await websocket.close()

    async def private(self, request: Request):
        return {"private": request.cookies.get("laomedo_private_session")}

    def test_private_session_is_isolated_by_port(self):
        cookie = (
            "laomedo_private_session=unscoped; "
            "laomedo_profile_55753_laomedo_private_session=foreign; "
            "laomedo_profile_17884_laomedo_private_session=selected"
        )
        self.assertEqual(
            self.client.get("/private", headers={"Cookie": cookie}).json()["private"],
            "selected",
        )

    def test_only_selected_preview_cookies_reach_http_and_websocket_auth(self):
        cookie = "access_token_lf=foreign; refresh_token_lf=foreign; laomedo_profile_55753_access_token_lf=foreign; laomedo_profile_17884_access_token_lf=selected; laomedo_profile_17884_refresh_token_lf=refresh; theme=dark"
        self.assertEqual(
            self.client.get("/read", headers={"Cookie": cookie}).json(),
            {"selected": True, "refresh": True, "unrelated": "dark"},
        )
        with self.client.websocket_connect(
            "/socket", headers={"Cookie": cookie}
        ) as websocket:
            self.assertEqual(websocket.receive_json(), {"selected": True})
        self.assertFalse(
            self.client.get(
                "/read",
                headers={
                    "Cookie": "access_token_lf=selected; laomedo_profile_55753_access_token_lf=selected"
                },
            ).json()["selected"]
        )

    def test_unrelated_permissive_cookie_names_and_values_do_not_break_auth(self):
        cookie = "[other]=value; theme=two words,with spaces; laomedo_profile_17884_access_token_lf=selected"
        response = self.client.get("/read", headers={"Cookie": cookie})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {"selected": True, "refresh": False, "unrelated": "two words,with spaces"},
        )

    def test_login_and_logout_rename_only_owned_cookies_preserving_attributes(self):
        headers = self.client.post("/login").headers.get_list("set-cookie")
        access = next(
            value
            for value in headers
            if value.startswith("laomedo_profile_17884_access_token_lf=")
        )
        for attribute in (
            "HttpOnly",
            "Secure",
            "SameSite=strict",
            "Max-Age=90",
            "Path=/",
        ):
            self.assertIn(attribute, access)
        self.assertTrue(any(value.startswith("theme=dark;") for value in headers))
        expired = self.client.post("/logout").headers.get_list("set-cookie")
        self.assertEqual(len(expired), 2)
        for value in expired:
            self.assertTrue(value.startswith("laomedo_profile_17884_"))
            self.assertIn("Max-Age=0", value)
            self.assertIn("HttpOnly", value)
