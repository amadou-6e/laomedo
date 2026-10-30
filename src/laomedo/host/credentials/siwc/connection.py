"""Single-user local Sign in with ChatGPT connection for Codex plan usage.

The broker owns rotating credentials outside Git. Callers receive an access
token only for the credential-bearing controller; tool executors never receive
this store or the token. OAuth errors are reduced to fixed categories."""

from __future__ import annotations
from laomedo.host.credentials.siwc.models import (
    OAuthAccount,
    OAuthAttempt,
    OAuthAuthorizationRequest,
    OAuthCodeExchange,
)

from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler
from uuid import uuid4
import base64
import hashlib
import json
from laomedo.host.credentials.siwc.settings import AUTH_ORIGIN
from laomedo.host.credentials.siwc.settings import MIN_DISPATCH_TTL
from laomedo.host.credentials.siwc.settings import NEEDED
from laomedo.host.credentials.siwc.settings import RESOURCE
from laomedo.host.credentials.siwc.settings import SCOPES
from laomedo.host.credentials.siwc.errors import AuthError
from laomedo.host.credentials.siwc.utils import _atomic_private
from laomedo.host.credentials.siwc.utils import _https_json
from laomedo.host.credentials.siwc.utils import _locked
from laomedo.host.credentials.siwc.utils import _outside_git
from laomedo.host.credentials.siwc.utils import _restrict_windows_directory
from laomedo.host.credentials.siwc.utils import _revoke
from laomedo.host.credentials.siwc.utils import _verify_id_token
import os
import secrets
import time


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise AuthError("auth_redirect_rejected")


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
            fd = os.open(self.lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "wb") as stream:
                stream.write(b"0")
        self.host_path = self.root / "host.json"
        if not self.host_path.exists():
            _atomic_private(
                self.host_path, {"ext_agent_host_id": "urn:uuid:" + str(uuid4())}
            )
        self.host_id = json.loads(self.host_path.read_text())["ext_agent_host_id"]

    def _path(self, client_id: str) -> Path:
        if not isinstance(client_id, str) or not client_id.startswith("oaiapp_"):
            raise AuthError("auth_client_invalid")
        return self.accounts / (
            hashlib.sha256(client_id.encode()).hexdigest() + ".json"
        )

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
        """Construct one private PKCE attempt after the existing callback admission."""
        parts = urlsplit(redirect_uri)
        if (
            parts.scheme != "http"
            or parts.hostname != "127.0.0.1"
            or parts.path != "/auth/callback"
            or parts.query
            or parts.fragment
        ):
            raise AuthError("auth_redirect_uri_invalid")
        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        previous = None
        hints = {}
        if client_id is None:
            hints["agent_name_hint"] = "Laomedo"
        else:
            previous = self._account(client_id)
            if previous.get("id_token"):
                hints["id_token_hint"] = previous["id_token"]
            if previous.get("email"):
                hints["login_hint"] = previous["email"]
        authorization = OAuthAuthorizationRequest(
            client_id=client_id or "dynamic_agent_client",
            ext_agent_host_id=self.host_id,
            redirect_uri=redirect_uri,
            scope=SCOPES,
            resource=RESOURCE,
            state=state,
            nonce=nonce,
            code_challenge=base64.urlsafe_b64encode(
                hashlib.sha256(verifier.encode()).digest()
            )
            .rstrip(b"=")
            .decode(),
            **hints,
        )
        return OAuthAttempt(
            url=AUTH_ORIGIN + "/api/accounts/authorize?" + authorization.to_query(),
            state=state,
            nonce=nonce,
            verifier=verifier,
            redirect_uri=redirect_uri,
            client_id=client_id,
            previous_subject=previous.get("subject") if previous else None,
        ).to_private_payload()

    def finish(
        self,
        attempt: dict,
        callback: dict,
        *,
        exchange=_https_json,
        verify=_verify_id_token,
    ) -> dict:
        if not secrets.compare_digest(str(callback.get("state", "")), attempt["state"]):
            raise AuthError("auth_state_mismatch")
        if callback.get("error"):
            raise AuthError(
                "auth_consent_denied"
                if callback["error"] == "access_denied"
                else "auth_callback_failed"
            )
        client_id = callback.get("client_id") or attempt["client_id"]
        if (
            attempt["client_id"]
            and client_id != attempt["client_id"]
            or not client_id
            or client_id == "dynamic_agent_client"
        ):
            raise AuthError("auth_client_mismatch")
        self._path(client_id)
        code = callback.get("code")
        if not isinstance(code, str) or not code:
            raise AuthError("auth_code_missing")
        response = exchange(
            AUTH_ORIGIN + "/api/accounts/oauth/token",
            fields=OAuthCodeExchange(
                client_id=client_id,
                code=code,
                code_verifier=attempt["verifier"],
                redirect_uri=attempt["redirect_uri"],
                resource=RESOURCE,
            ).to_private_payload(),
        )
        claims = verify(response.get("id_token"), client_id, attempt["nonce"])
        if (
            attempt.get("previous_subject")
            and claims["sub"] != attempt["previous_subject"]
        ):
            raise AuthError("auth_account_mismatch")
        scopes = set(str(response.get("scope", "")).split())
        if not NEEDED.issubset(scopes):
            raise AuthError("auth_scope_missing")
        if not all(
            isinstance(response.get(key), str) and response[key]
            for key in ("access_token", "refresh_token", "id_token")
        ):
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
            account = OAuthAccount(
                client_id=client_id,
                subject=claims["sub"],
                issuer=claims["iss"],
                email=claims.get("email"),
                ext_agent_host_id=self.host_id,
                id_token=response["id_token"],
                access_token=response["access_token"],
                refresh_token=response["refresh_token"],
                scopes=sorted(scopes),
                expires_at=time.time() + expires_in,
                generation=generation,
                state="active",
            ).to_private_record()
            _atomic_private(self._path(client_id), account)
            _atomic_private(self.root / "active.json", {"client_id": client_id})
        return self.summary(account)

    @staticmethod
    def summary(account: dict) -> dict:
        return {
            "credential_mode": "chatgpt_plan_oauth",
            "credential_ref": "chatgpt:"
            + hashlib.sha256(account["client_id"].encode()).hexdigest()[:16],
            "provider_subject_hash": "sha256:"
            + hashlib.sha256(account["subject"].encode()).hexdigest(),
            "generation": account["generation"],
            "auth_outcome": account["state"],
        }

    def access_token(self, *, refresh=_https_json) -> tuple[str, dict]:
        with _locked(self.lock_path):
            account = self.active()
            if account.get("state") != "active":
                raise AuthError(
                    "auth_refresh_unknown"
                    if account.get("state") in {"refresh_unknown", "refresh_in_flight"}
                    else "auth_revoked"
                )
            if not NEEDED.issubset(set(account.get("scopes", []))):
                raise AuthError("auth_scope_missing")
            if account["expires_at"] > time.time() + MIN_DISPATCH_TTL:
                return account["access_token"], self.summary(account)
            # Persist uncertainty before sending a rotating refresh token.
            # A crash or malformed success response must never replay it.
            account["state"] = "refresh_in_flight"
            _atomic_private(self._path(account["client_id"]), account)
            try:
                response = refresh(
                    AUTH_ORIGIN + "/api/accounts/oauth/token",
                    fields={
                        "grant_type": "refresh_token",
                        "client_id": account["client_id"],
                        "refresh_token": account["refresh_token"],
                        "resource": RESOURCE,
                    },
                )
                scopes = (
                    set(str(response["scope"]).split())
                    if "scope" in response
                    else set(account["scopes"])
                )
                if not NEEDED.issubset(scopes):
                    raise AuthError("auth_scope_missing")
                if not all(
                    isinstance(response.get(key), str) and response[key]
                    for key in ("access_token", "refresh_token")
                ):
                    raise AuthError("auth_refresh_response_invalid")
                expires_in = response.get("expires_in")
                if type(expires_in) is not int or expires_in < 60:
                    raise AuthError("auth_refresh_response_invalid")
            except Exception:
                account["state"] = "refresh_unknown"
                _atomic_private(self._path(account["client_id"]), account)
                raise AuthError("auth_refresh_unknown") from None
            account.update(
                access_token=response["access_token"],
                refresh_token=response["refresh_token"],
                scopes=sorted(scopes),
                expires_at=time.time() + expires_in,
                generation=account["generation"] + 1,
                state="active",
            )
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
                confirmed = (
                    revoke(account["refresh_token"], account["client_id"]) is True
                )
            except Exception:
                confirmed = False
        with _locked(self.lock_path):
            latest = self._account(account["client_id"])
            if (
                latest.get("state") == "revocation_pending"
                and latest.get("generation") == account["generation"]
            ):
                latest.update(
                    state="revoked",
                    access_token=None,
                    refresh_token=None,
                    id_token=None,
                    generation=latest["generation"] + 1,
                )
                _atomic_private(self._path(latest["client_id"]), latest)
        return {"auth_outcome": "signed_out", "remote_revocation_confirmed": confirmed}
