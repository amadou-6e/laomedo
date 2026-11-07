"""Access-only handoff from the existing Console login, never a personal profile copy."""

import hashlib
import json
import os
import time
from pathlib import Path

from laomedo.agents.agents.opencode.auth.utils import console_provider, credential
from laomedo.agents.agents.opencode.utils import check_auth_fresh
from laomedo.host.private_state.models import DirectoryPermissionPolicy
from laomedo.host.private_state.utils import prepare_private_directory
from laomedo.host.private_state.windows import WindowsDirectorySecurity


def main():
    root = Path("C:/CodeWorkspace/laomedo")
    evidence = root / "claude-review.local/agents-250-20261107"
    state = Path(
        json.loads((evidence / "runtime-path.json").read_text(encoding="utf-8"))["path"]
    )
    profile = state / "opencode-profile"
    database = Path(os.environ["USERPROFILE"]) / ".local/share/opencode/opencode.db"
    provider_auth = Path(os.environ["USERPROFILE"]) / ".local/share/opencode/auth.json"
    if not database.is_file() and not provider_auth.is_file():
        result = {
            "ready": False,
            "code": "opencode_active_console_account_required",
            "submitted_turns": 0,
        }
    else:
        system = WindowsDirectorySecurity().system_directory()
        policy = DirectoryPermissionPolicy(
            whoami=system / "whoami.exe",
            icacls=system / "icacls.exe",
            environment={
                key: os.environ[key]
                for key in ["SystemRoot", "WINDIR"]
                if key in os.environ
            },
            deadline=time.monotonic() + 30,
        )
        prepare_private_directory(profile, policy=policy)
        console = None
        if database.is_file():
            try:
                console = console_provider(
                    database, include_routing=True, include_expiry=True
                )
            except ValueError as error:
                if str(error) != "opencode_active_console_account_required":
                    raise
        if console is not None:
            selected, organization, routing, validity = console
        else:
            saved = json.loads(provider_auth.read_text(encoding="utf-8"))
            entry = saved.get("opencode-go", {})
            if entry.get("type") != "api":
                raise ValueError("opencode_private_auth_required")
            selected = {"type": "api", "key": credential(entry.get("key"))}
            organization = routing = None
            validity = {"credential_mode": "provider_key", "expires_at_ms": None}
        values = {
            "auth.json": {"opencode-go": selected},
            "auth-validity.json": {
                **validity,
                "credential_sha256": hashlib.sha256(
                    selected["key"].encode()
                ).hexdigest(),
            },
        }
        if routing is not None:
            values["provider-options.json"] = {
                "provider": {
                    "opencode-go": {
                        **routing,
                        "options": {"headers": {"x-opencode-org-id": organization}},
                    }
                }
            }
        for name, value in values.items():
            (profile / name).write_text(json.dumps(value), encoding="utf-8")
        check_auth_fresh(profile)
        result = {
            "ready": True,
            "copied_provider_count": 1,
            "access_only": True,
            "private_directory_verified": True,
            "submitted_turns": 0,
        }
    (evidence / "opencode-readiness.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        code = str(error)
        safe = (
            code
            if code.startswith(("opencode_", "private_state_"))
            and code.replace("_", "").isalnum()
            else "opencode_access_setup_unavailable"
        )
        print(json.dumps({"ready": False, "code": safe, "submitted_turns": 0}))
        raise SystemExit(1)
