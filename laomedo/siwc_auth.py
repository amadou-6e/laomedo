"""Single-user local Sign in with ChatGPT connection for Codex plan usage.

The broker owns rotating credentials outside Git. Callers receive an access
token only for the credential-bearing controller; tool executors never receive
this store or the token. OAuth errors are reduced to fixed categories.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
import csv
import hashlib
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import os
from pathlib import Path
import secrets
import ssl
import subprocess
import time
from urllib.parse import urlencode, parse_qs, urlsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, build_opener, HTTPRedirectHandler
from uuid import uuid4
import webbrowser

import jwt


AUTH_ORIGIN = "https://auth.openai.com"
RESOURCE = "https://api.openai.com/v1"
SCOPES = "openid profile email offline_access resource.invoke chatgpt.tokens.use.direct"
NEEDED = frozenset({"openid", "offline_access", "resource.invoke",
                    "chatgpt.tokens.use.direct"})
MIN_DISPATCH_TTL = 300


class AuthError(ValueError):
    """A fixed category safe for run records and logs."""


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise AuthError("auth_redirect_rejected")


def _https_json(url: str, *, fields: dict | None = None) -> dict:
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname != "auth.openai.com" or
            parts.username or parts.password or parts.fragment):
        raise AuthError("auth_endpoint_untrusted")
    body = urlencode(fields).encode() if fields is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        with build_opener(_NoRedirect()).open(
                Request(url, data=body, headers=headers), timeout=20) as response:
            result = json.load(response)
    except AuthError:
        raise
    except HTTPError as exc:
        # Status is safe to report; never include the URL, headers, or body.
        status = exc.code if type(exc.code) is int and 400 <= exc.code <= 599 else 0
        exc.close()
        raise AuthError(f"auth_http_{status}") from None
    except URLError as exc:
        if isinstance(exc.reason, ssl.SSLCertVerificationError):
            raise AuthError("auth_tls_verify_failed") from None
        raise AuthError("auth_transport_failed") from None
    except ssl.SSLCertVerificationError:
        raise AuthError("auth_tls_verify_failed") from None
    except (TimeoutError, OSError):
        raise AuthError("auth_transport_failed") from None
    except (ValueError, TypeError):
        raise AuthError("auth_response_invalid") from None
    except Exception:
        raise AuthError("auth_exchange_failed") from None
    if not isinstance(result, dict):
        raise AuthError("auth_response_invalid")
    return result


def _verify_id_token(token: str, client_id: str, nonce: str) -> dict:
    try:
        discovery = _https_json(AUTH_ORIGIN + "/.well-known/openid-configuration")
        jwks_uri = discovery.get("jwks_uri")
        parts = urlsplit(jwks_uri)
        if (parts.scheme != "https" or parts.hostname != "auth.openai.com" or
                parts.username or parts.password or parts.fragment):
            raise AuthError("auth_jwks_untrusted")
        key = jwt.PyJWKClient(jwks_uri).get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"],
                            audience=client_id, issuer=AUTH_ORIGIN,
                            options={"require": ["exp", "iss", "aud", "sub"]})
        if not isinstance(claims.get("sub"), str) or not secrets.compare_digest(
                str(claims.get("nonce", "")), nonce):
            raise AuthError("auth_identity_invalid")
        return claims
    except AuthError:
        raise
    except Exception:
        raise AuthError("auth_identity_invalid") from None


def _revoke(refresh_token: str, client_id: str) -> bool:
    discovery = _https_json(AUTH_ORIGIN + "/.well-known/openid-configuration")
    endpoint = discovery.get("revocation_endpoint")
    parts = urlsplit(endpoint)
    if (parts.scheme != "https" or parts.hostname != "auth.openai.com" or
            parts.username or parts.password or parts.fragment):
        raise AuthError("auth_revocation_endpoint_untrusted")
    data = urlencode({"token": refresh_token,
                      "token_type_hint": "refresh_token",
                      "client_id": client_id}).encode()
    with build_opener(_NoRedirect()).open(Request(endpoint, data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"}),
        timeout=20) as response:
        return response.status == 200


def _atomic_private(path: Path, value: dict) -> None:
    pending = path.with_name(path.name + ".pending-" + uuid4().hex)
    data = json.dumps(value, sort_keys=True).encode("utf-8")
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def _outside_git(path: Path) -> Path:
    original = path.expanduser().absolute()
    if any(parent.is_symlink() for parent in (original, *original.parents)):
        raise AuthError("auth_store_symlink_rejected")
    path = original.resolve()
    if any((parent / ".git").exists()
                                for parent in (path, *path.parents)):
        raise AuthError("auth_store_must_be_outside_git")
    return path


def _restrict_windows_directory(path: Path) -> None:
    if os.name != "nt":
        os.chmod(path, 0o700)
        return
    identity = subprocess.run(["whoami", "/user", "/fo", "csv", "/nh"],
                              capture_output=True, text=True, timeout=10)
    if identity.returncode:
        raise AuthError("auth_store_permissions_unverified")
    rows = list(csv.reader(identity.stdout.splitlines()))
    if len(rows) != 1 or len(rows[0]) != 2 or not rows[0][1].startswith("S-"):
        raise AuthError("auth_store_permissions_unverified")
    sid = rows[0][1]
    result = subprocess.run(["icacls", str(path), "/inheritance:r",
                             "/grant:r", "*" + sid + ":(OI)(CI)F"],
                            capture_output=True, text=True, timeout=15)
    if result.returncode:
        raise AuthError("auth_store_permissions_unverified")


@contextmanager
def _locked(path: Path):
    fd = os.open(path, os.O_RDWR, 0o600)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt
            deadline = time.monotonic() + 35
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise AuthError("auth_refresh_lock_unavailable") from None
                    time.sleep(.1)
        else:
            import fcntl
            fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            os.lseek(fd, 0, os.SEEK_SET)
            if os.name == "nt":
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


class ChatGPTConnection:
    def __init__(self, root: Path):
        self.root = _outside_git(root)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        _restrict_windows_directory(self.root)
        self.accounts = self.root / "accounts"
        self.accounts.mkdir(exist_ok=True, mode=0o700)
        _restrict_windows_directory(self.accounts)
        self.lock_path = self.root / "refresh.lock"
        if not self.lock_path.exists():
            fd = os.open(self.lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                         0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(b"0")
        self.host_path = self.root / "host.json"
        if not self.host_path.exists():
            _atomic_private(self.host_path, {"ext_agent_host_id": "urn:uuid:" +
                                                       str(uuid4())})
        self.host_id = json.loads(self.host_path.read_text())[
            "ext_agent_host_id"]

    def _path(self, client_id: str) -> Path:
        if not isinstance(client_id, str) or not client_id.startswith("oaiapp_"):
            raise AuthError("auth_client_invalid")
        return self.accounts / (hashlib.sha256(client_id.encode()).hexdigest() +
                                ".json")

    def _account(self, client_id: str) -> dict:
        path = self._path(client_id)
        if not path.exists():
            raise AuthError("auth_account_missing")
        account = json.loads(path.read_text(encoding="utf-8"))
        if account.get("client_id") != client_id:
            raise AuthError("auth_account_mismatch")
        return account

    def active(self) -> dict:
        pointer = self.root / "active.json"
        if not pointer.exists():
            raise AuthError("auth_account_missing")
        client_id = json.loads(pointer.read_text())["client_id"]
        return self._account(client_id)

    def begin(self, redirect_uri: str, *, client_id: str | None = None) -> dict:
        parts = urlsplit(redirect_uri)
        if (parts.scheme != "http" or parts.hostname != "127.0.0.1" or
                parts.path != "/auth/callback" or parts.query or parts.fragment):
            raise AuthError("auth_redirect_uri_invalid")
        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        params = {"client_id": client_id or "dynamic_agent_client",
                  "ext_agent_host_id": self.host_id,
                  "response_type": "code", "redirect_uri": redirect_uri,
                  "scope": SCOPES, "resource": RESOURCE, "state": state,
                  "nonce": nonce, "code_challenge_method": "S256",
                  "code_challenge": base64.urlsafe_b64encode(
                      hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()}
        previous = None
        if client_id is None:
            params["agent_name_hint"] = "Laomedo"
        else:
            previous = self._account(client_id)
            if previous.get("id_token"):
                params["id_token_hint"] = previous["id_token"]
            if previous.get("email"):
                params["login_hint"] = previous["email"]
        return {"url": AUTH_ORIGIN + "/api/accounts/authorize?" +
                urlencode(params), "state": state, "nonce": nonce,
                "verifier": verifier, "redirect_uri": redirect_uri,
                "client_id": client_id, "previous_subject":
                    previous.get("subject") if previous else None}

    def finish(self, attempt: dict, callback: dict, *, exchange=_https_json,
               verify=_verify_id_token) -> dict:
        if not secrets.compare_digest(str(callback.get("state", "")),
                                      attempt["state"]):
            raise AuthError("auth_state_mismatch")
        if callback.get("error"):
            raise AuthError("auth_consent_denied" if callback["error"] ==
                            "access_denied" else "auth_callback_failed")
        client_id = callback.get("client_id") or attempt["client_id"]
        if (attempt["client_id"] and client_id != attempt["client_id"] or
                not client_id or client_id == "dynamic_agent_client"):
            raise AuthError("auth_client_mismatch")
        self._path(client_id)
        code = callback.get("code")
        if not isinstance(code, str) or not code:
            raise AuthError("auth_code_missing")
        response = exchange(AUTH_ORIGIN + "/api/accounts/oauth/token", fields={
            "grant_type": "authorization_code", "client_id": client_id,
            "code": code, "code_verifier": attempt["verifier"],
            "redirect_uri": attempt["redirect_uri"], "resource": RESOURCE})
        claims = verify(response.get("id_token"), client_id, attempt["nonce"])
        if (attempt.get("previous_subject") and
                claims["sub"] != attempt["previous_subject"]):
            raise AuthError("auth_account_mismatch")
        scopes = set(str(response.get("scope", "")).split())
        if not NEEDED.issubset(scopes):
            raise AuthError("auth_scope_missing")
        if not all(isinstance(response.get(key), str) and response[key]
                   for key in ("access_token", "refresh_token", "id_token")):
            raise AuthError("auth_token_response_invalid")
        expires_in = response.get("expires_in")
        if type(expires_in) is not int or expires_in < 60:
            raise AuthError("auth_token_response_invalid")
        with _locked(self.lock_path):
            try:
                prior = self._account(client_id)
            except AuthError as exc:
                if str(exc) != "auth_account_missing":
                    raise
                prior = {}
            if prior and prior.get("subject") != claims["sub"]:
                raise AuthError("auth_account_mismatch")
            generation = prior.get("generation", 0) + 1
            account = {"client_id": client_id, "subject": claims["sub"],
                       "issuer": claims["iss"], "email": claims.get("email"),
                       "ext_agent_host_id": self.host_id,
                       "id_token": response["id_token"],
                       "access_token": response["access_token"],
                       "refresh_token": response["refresh_token"],
                       "scopes": sorted(scopes), "expires_at": time.time() + expires_in,
                       "generation": generation, "state": "active"}
            _atomic_private(self._path(client_id), account)
            _atomic_private(self.root / "active.json", {"client_id": client_id})
        return self.summary(account)

    @staticmethod
    def summary(account: dict) -> dict:
        return {"credential_mode": "chatgpt_plan_oauth",
                "credential_ref": "chatgpt:" + hashlib.sha256(
                    account["client_id"].encode()).hexdigest()[:16],
                "provider_subject_hash": "sha256:" + hashlib.sha256(
                    account["subject"].encode()).hexdigest(),
                "generation": account["generation"],
                "auth_outcome": account["state"]}

    def access_token(self, *, refresh=_https_json) -> tuple[str, dict]:
        with _locked(self.lock_path):
            account = self.active()
            if account.get("state") != "active":
                raise AuthError("auth_refresh_unknown" if account.get("state") in
                                {"refresh_unknown", "refresh_in_flight"} else
                                "auth_revoked")
            if not NEEDED.issubset(set(account.get("scopes", []))):
                raise AuthError("auth_scope_missing")
            if account["expires_at"] > time.time() + MIN_DISPATCH_TTL:
                return account["access_token"], self.summary(account)
            # Persist uncertainty before sending a rotating refresh token.
            # A crash or malformed success response must never replay it.
            account["state"] = "refresh_in_flight"
            _atomic_private(self._path(account["client_id"]), account)
            try:
                response = refresh(AUTH_ORIGIN + "/api/accounts/oauth/token",
                                   fields={"grant_type": "refresh_token",
                                           "client_id": account["client_id"],
                                           "refresh_token": account["refresh_token"],
                                           "resource": RESOURCE})
                scopes = (set(str(response["scope"]).split()) if "scope" in response
                          else set(account["scopes"]))
                if not NEEDED.issubset(scopes):
                    raise AuthError("auth_scope_missing")
                if not all(isinstance(response.get(key), str) and response[key]
                           for key in ("access_token", "refresh_token")):
                    raise AuthError("auth_refresh_response_invalid")
                expires_in = response.get("expires_in")
                if type(expires_in) is not int or expires_in < 60:
                    raise AuthError("auth_refresh_response_invalid")
            except Exception:
                account["state"] = "refresh_unknown"
                _atomic_private(self._path(account["client_id"]), account)
                raise AuthError("auth_refresh_unknown") from None
            account.update(access_token=response["access_token"],
                           refresh_token=response["refresh_token"],
                           scopes=sorted(scopes), expires_at=time.time() + expires_in,
                           generation=account["generation"] + 1, state="active")
            _atomic_private(self._path(account["client_id"]), account)
            return account["access_token"], self.summary(account)

    def switch(self, client_id: str) -> dict:
        with _locked(self.lock_path):
            account = self._account(client_id)
            if account.get("state") != "active":
                raise AuthError("auth_account_unavailable")
            _atomic_private(self.root / "active.json", {"client_id": client_id})
            return self.summary(account)

    def sign_out(self, *, revoke=_revoke) -> dict:
        with _locked(self.lock_path):
            account = self.active()
            # Stop dispatch and running-controller checks before a potentially
            # slow remote revocation request.
            account["state"] = "revocation_pending"
            _atomic_private(self._path(account["client_id"]), account)
            (self.root / "active.json").unlink(missing_ok=True)
        confirmed = False
        if revoke is not None:
            try:
                confirmed = revoke(account["refresh_token"],
                                   account["client_id"]) is True
            except Exception:
                confirmed = False
        with _locked(self.lock_path):
            latest = self._account(account["client_id"])
            if (latest.get("state") == "revocation_pending" and
                    latest.get("generation") == account["generation"]):
                latest.update(state="revoked", access_token=None,
                              refresh_token=None, id_token=None,
                              generation=latest["generation"] + 1)
                _atomic_private(self._path(latest["client_id"]), latest)
        return {"auth_outcome": "signed_out",
                "remote_revocation_confirmed": confirmed}


def browser_connect(store: ChatGPTConnection, *, client_id=None,
                    timeout=180) -> dict:
    """Open the system browser and handle one loopback OAuth callback."""
    received = {}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def do_GET(self):
            parts = urlsplit(self.path)
            if parts.path != "/auth/callback":
                self.send_error(404)
                return
            for key, values in parse_qs(parts.query).items():
                if len(values) == 1:
                    received[key] = values[0]
            body = b"Laomedo received the ChatGPT response. You may close this tab."
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    with HTTPServer(("127.0.0.1", 0), Handler) as server:
        server.timeout = timeout
        attempt = store.begin(
            f"http://127.0.0.1:{server.server_port}/auth/callback",
            client_id=client_id)
        # Authorization URL may contain id_token_hint. Never print or log it.
        if not webbrowser.open(attempt["url"]):
            raise AuthError("auth_browser_unavailable")
        server.handle_request()
    if not received:
        raise AuthError("auth_callback_timeout")
    return store.finish(attempt, received)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Laomedo local ChatGPT connection")
    parser.add_argument("--store", type=Path, required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    connect = sub.add_parser("connect")
    connect.add_argument("--client-id")
    sub.add_parser("status")
    sub.add_parser("list")
    switch = sub.add_parser("switch")
    switch.add_argument("client_id")
    sub.add_parser("sign-out")
    args = parser.parse_args()
    try:
        store = ChatGPTConnection(args.store)
        if args.action == "connect":
            result = browser_connect(store, client_id=args.client_id)
        elif args.action == "status":
            result = store.summary(store.active())
        elif args.action == "list":
            result = {"accounts": [
                {"client_id": entry["client_id"], **store.summary(entry)}
                for path in sorted(store.accounts.glob("*.json"))
                if isinstance((entry := json.loads(path.read_text())), dict)]}
        elif args.action == "switch":
            result = store.switch(args.client_id)
        else:
            result = store.sign_out()
        print(json.dumps(result, sort_keys=True))
    except AuthError as exc:
        print(json.dumps({"auth_outcome": "failed", "error_category": str(exc)}))
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
