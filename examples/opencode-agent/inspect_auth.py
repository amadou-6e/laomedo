"""Emit only credential-presence/equality booleans, never credential material."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from laomedo.opencode_auth import console_provider, credential


def main():
    config = json.loads(subprocess.run(["opencode.cmd", "debug", "config"], capture_output=True,
                                      text=True, check=True, timeout=45).stdout)
    go = config.get("provider", {}).get("opencode-go", {}).get("options", {})
    key = go.get("apiKey")
    selected, current_org = console_provider(
        Path(os.environ["USERPROFILE"]) / ".local/share/opencode/opencode.db")
    private = Path(os.environ["LOCALAPPDATA"]) / "Laomedo/opencode-27/profile"
    saved = json.loads((private / "auth.json").read_text())["opencode-go"]["key"]
    options = json.loads((private / "provider-options.json").read_text())
    organization = options["provider"]["opencode-go"]["options"]["headers"]["x-opencode-org-id"]
    print(json.dumps({"provider": "opencode-go", "configured_key_present": bool(key),
        "actual_console_credential_present": bool(credential(selected["key"])),
        "key_is_redaction": key in {"[REDACTED]", "[redacted]", "<redacted>", "********"} or "***" in str(key),
        "private_key_matches_console_config": saved == selected["key"],
        "private_organization_matches_console_config": organization == current_org}))


if __name__ == "__main__":
    main()
