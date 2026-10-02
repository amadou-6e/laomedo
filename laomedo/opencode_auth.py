"""Read the active Console account without copying profiles or refresh tokens."""
import json
import re
from contextlib import closing
from pathlib import Path
import sqlite3
import time
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.parse import urlsplit


def credential(value):
    if (not isinstance(value, str) or not value.strip() or
            value.lower() in {"[redacted]", "<redacted>"} or
            "***" in value or value.startswith("CANARY-") or value.startswith("{")):
        raise ValueError("opencode_real_credential_required")
    return value


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError("opencode_auth_redirect_rejected")


def console_provider(database, *, fetch=None, include_routing=False, include_expiry=False):
    """Return only the Go credential and organization routing header, never log them."""
    with closing(sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)) as db:
        db.row_factory = sqlite3.Row
        row = db.execute("SELECT a.access_token, a.token_expiry, a.url, s.active_org_id "
            "FROM account a JOIN account_state s ON a.id=s.active_account_id").fetchone()
    if row is None or not row["active_org_id"]:
        raise ValueError("opencode_active_console_account_required")
    token = credential(row["access_token"])
    if not row["token_expiry"] or row["token_expiry"] <= int(time.time() * 1000) + 60000:
        raise ValueError("opencode_console_token_refresh_required")
    origin = urlsplit(row["url"])
    if (origin.scheme != "https" or origin.hostname != "opencode.ai" or
            origin.username or origin.password or origin.query or origin.fragment or
            origin.path not in ("", "/", "/console", "/console/")):
        raise ValueError("opencode_console_origin_not_allowed")
    headers = {"Authorization": "Bearer " + token, "x-org-id": row["active_org_id"],
               "Accept": "application/json", "User-Agent": "opencode/1.18.33"}
    if fetch is None:
        def fetch(url, headers):
            with build_opener(NoRedirect()).open(Request(url, headers=headers), timeout=30) as response:
                return json.load(response)
    remote = fetch(row["url"].rstrip("/") + "/api/config", headers)
    provider = remote.get("config", {}).get("provider", {}).get("opencode-go", {})
    options = provider.get("options", {})
    key = options.get("apiKey")
    token_bound = key == "{env:OPENCODE_CONSOLE_TOKEN}"
    if token_bound:
        key = token
    key = credential(key)
    org = options.get("headers", {}).get("x-opencode-org-id")
    if not isinstance(org, str) or org != row["active_org_id"]:
        raise ValueError("opencode_organization_context_mismatch")
    selected = {"type": "api", "key": key}
    if include_routing:
        api = provider.get("api")
        if api != "https://opencode.ai/inference/go/openai/v1" or provider.get("npm") != "@ai-sdk/openai-compatible":
            raise ValueError("opencode_console_provider_routing_not_allowed")
        names = list(provider.get("models", {}))
        if not names or any(not re.fullmatch(r"[A-Za-z0-9_.:-]+", name) for name in names):
            raise ValueError("opencode_console_models_required")
        models = {}
        for name in names:
            native = provider["models"][name].get("provider", {})
            route = {}
            if "npm" in native:
                if native["npm"] not in {"@ai-sdk/openai", "@ai-sdk/openai-compatible", "@ai-sdk/anthropic"}:
                    raise ValueError("opencode_model_sdk_not_allowed")
                route["npm"] = native["npm"]
            if "api" in native:
                endpoint = urlsplit(native["api"])
                if (endpoint.scheme != "https" or endpoint.hostname != "opencode.ai" or
                        endpoint.username or endpoint.password or endpoint.query or endpoint.fragment or
                        not endpoint.path.startswith("/inference/go/")):
                    raise ValueError("opencode_model_endpoint_not_allowed")
                route["api"] = native["api"]
            models[name] = {"provider": route} if route else {}
        result = (selected, org, {"api": api, "npm": provider["npm"], "models": models})
        return (*result, {"credential_mode": "console_token" if token_bound else "provider_key",
                          "expires_at_ms": row["token_expiry"] if token_bound else None}) if include_expiry else result
    if include_expiry:
        return selected, org, {"credential_mode": "console_token" if token_bound else "provider_key",
                               "expires_at_ms": row["token_expiry"] if token_bound else None}
    return selected, org
