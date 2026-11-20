"""Rotate the one connected Codex account in the isolated chat acceptance runtime.

Uses the normal host broker and its process-shared refresh lock. No token is
printed, copied into a probe, or written outside the existing private store.
The larger borrow threshold requests renewal without editing expiry metadata.
"""

import json
import os
from pathlib import Path
from unittest.mock import patch

from laomedo.host.credentials.siwc.connection import ChatGPTConnection

runtime = (
    Path(os.environ["LOCALAPPDATA"]) / "Laomedo/acceptance/assistant-saved-293-01a1ba85"
)
selected = []
for index in (runtime / "provider-connections").glob("*/connections.json"):
    for record in json.loads(index.read_text(encoding="utf-8"))["connections"]:
        if (
            record.get("provider", "codex") == "codex"
            and record["lifecycle"] == "connected"
        ):
            selected.append((index, record))
if len(selected) != 1:
    raise SystemExit("Expected exactly one connected acceptance Codex account")
index, record = selected[0]
broker = ChatGPTConnection(index.parent / record["credential_id"])
prior = broker.account(record["client_id"])
try:
    with patch("laomedo.host.credentials.siwc.connection.MIN_DISPATCH_TTL", 10**12):
        token, observation = broker.access_token(record["client_id"])
    current = broker.account(record["client_id"])
    unchanged = json.loads(index.read_text(encoding="utf-8"))["connections"]
    admitted = next(
        item for item in unchanged if item["connection_id"] == record["connection_id"]
    )
    print(
        json.dumps(
            {
                "token_rotated": token != prior["access_token"],
                "credential_generation_advanced": current["generation"]
                > prior["generation"],
                "account_identity_unchanged": current["subject"] == prior["subject"],
                "connection_generation_unchanged": admitted["generation"]
                == record["generation"],
                "host_state": current["state"],
            }
        )
    )
except Exception as failure:
    print("refresh_failed", type(failure).__name__)
    raise SystemExit(1)
