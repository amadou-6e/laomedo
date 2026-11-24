"""Bounded real OpenCode conflict and same-conversation recovery in the pilot clone."""

import argparse
import json
import os
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

from acceptance_shell import StorageAcceptance


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--conversation")
    arguments = parser.parse_args()
    acceptance = StorageAcceptance()
    acceptance.login()
    prefix = "/api/v1/laomedo/assistant"
    state = acceptance.request(prefix + "/storage")
    repository = next(
        row
        for row in state["repositories"]
        if row["name"] == "Repository storage validation"
    )
    checkout = Path(repository["path"]).resolve()
    expected = (
        Path(os.environ["LOCALAPPDATA"])
        / "Laomedo/acceptance/assistant-saved-293-01a1ba85/project-storage/checkouts"
    ).resolve()
    if not checkout.is_relative_to(expected):
        raise RuntimeError("wrong_acceptance_checkout")
    target = checkout / "agent-files/recovery-acceptance.md"
    identifier = arguments.conversation
    if identifier:
        acceptance.message(
            identifier,
            "Use Laomedo read_project_file to read recovery-acceptance.md from the connected agent files. Then use your normal shell to restore EXACTLY that returned content in project/agent-files/recovery-acceptance.md. Do not merge or change any other files. Reply only restored.",
        )
        if target.read_text(encoding="utf-8") != "External recovery version":
            raise RuntimeError("external_version_not_preserved")
        acceptance.message(
            identifier,
            "Using your normal shell, replace project/agent-files/recovery-acceptance.md with exactly Recovered final version, without a newline. Change no other file. Reply only done.",
        )
        if target.read_text(encoding="utf-8") != "Recovered final version":
            raise RuntimeError("recovered_write_not_persisted")
        print(
            json.dumps(
                {"conversation": identifier, "same_conversation_recovery": "passed"}
            )
        )
        return
    connection = next(
        row
        for row in acceptance.request(prefix + "/connections")["connections"]
        if row["provider"] == "opencode" and row["lifecycle"] == "connected"
    )
    models = acceptance.request(
        prefix
        + "/models?"
        + urlencode(
            {
                "provider": "opencode",
                "connection_id": connection["connection_id"],
                "connection_generation": connection["generation"],
            }
        )
    )["models"]
    model = next(row for row in models if row["id"].startswith("opencode-go/"))
    conversation = acceptance.request(
        prefix + "/conversations",
        {
            "provider": "opencode",
            "connection_id": connection["connection_id"],
            "connection_generation": connection["generation"],
            "model": model["id"],
            "effort": "low" if "low" in model["efforts"] else model["efforts"][0],
        },
    )
    identifier = conversation.get("id") or conversation["conversation"]["id"]
    acceptance.message(
        identifier,
        "Use your normal shell to write exactly Initial recovery version without a newline into project/agent-files/recovery-acceptance.md. Do not change any other files. Reply only done.",
    )
    if target.read_text(encoding="utf-8") != "Initial recovery version":
        raise RuntimeError("initial_write_not_persisted")
    target.write_text("External recovery version", encoding="utf-8")
    acceptance.request(
        prefix + "/conversations/" + identifier + "/messages",
        {
            "client_message_id": str(uuid4()),
            "text": "Use your normal shell to write exactly Shell conflicting version without a newline into project/agent-files/recovery-acceptance.md. Change no other file. Reply only done.",
        },
    )
    result = acceptance.wait(identifier)
    last = result["messages"][-1]
    if (
        last.get("error_code") != "assistant_storage_workspace_conflict"
        or last["state"] != "completed"
    ):
        raise RuntimeError("expected_completed_conflict_not_observed")
    if target.read_text(encoding="utf-8") != "External recovery version":
        raise RuntimeError("external_version_overwritten")
    print(
        json.dumps(
            {
                "conversation": identifier,
                "conflict": "passed",
                "send_unlocked": result["conversation"]["active_message_id"] is None,
            }
        )
    )


if __name__ == "__main__":
    main()
