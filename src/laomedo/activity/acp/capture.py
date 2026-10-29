"""Project observed ACP updates into Laomedo's existing activity vocabulary."""

import json

from laomedo.activity.runner.feed import receipt
from laomedo.activity.opencode.utils import sanitized


class AcpCapture:
    """Retain original ACP payloads separately from derived display items.

    Parameters
    ----------
    root : pathlib.Path
        Private run evidence directory, never the model's writable workspace.
    turn_id : str
        Host-assigned attempt identity, explicitly labelled as host provenance.
    """

    def __init__(self, root, turn_id):
        """Initialize prompt-local item state without creating provider identities."""
        self.root = root
        self.turn_id = turn_id
        self.items = {}
        self.message = 0
        self.message_id = None

    def append(self, method, params):
        """Persist a sanitized observation; normalized records are never native claims."""
        with self.root.joinpath("activity-events.jsonl").open(
            "a", encoding="utf-8"
        ) as log:
            log.write(
                json.dumps(receipt({"method": method, "params": sanitized(params)}))
                + "\n"
            )

    def begin(self, session_id, task):
        """Record the actual session binding and the host-submitted prompt."""
        self.append(
            "thread/started",
            {"thread": {"id": session_id}, "provenance": "ACP session binding"},
        )
        self.append(
            "turn/started",
            {
                "threadId": session_id,
                "turn": {"id": self.turn_id},
                "identity_source": "host_attempt",
            },
        )
        self.append(
            "item/completed",
            {
                "threadId": session_id,
                "turnId": self.turn_id,
                "item": {
                    "id": self.turn_id + ":prompt",
                    "type": "userMessage",
                    "text": task,
                    "provenance": "host_submitted_prompt",
                },
            },
        )

    def update(self, session_id, update):
        """Retain the ACP payload and derive display deltas using observed tool IDs."""
        self.append(
            "acp/sessionUpdate",
            {"sessionId": session_id, "turnId": self.turn_id, "update": update},
        )
        kind = update.get("sessionUpdate")
        item = None
        if kind in {"agent_message_chunk", "agent_thought_chunk"}:
            content = update.get("content", {})
            if content.get("type") != "text":
                return
            if self.message_id is None:
                self.message += 1
                self.message_id = self.turn_id + ":text:" + str(self.message)
            identity = update.get("messageId", self.message_id)
            item = self.items.setdefault(
                identity,
                {
                    "id": identity,
                    "type": "agentMessage"
                    if kind == "agent_message_chunk"
                    else "reasoning",
                    "text": "",
                    "provenance": "normalized ACP update",
                },
            )
            item["text"] += content["text"]
        elif kind in {"tool_call", "tool_call_update"}:
            self.message_id = None
            identity = update.get("toolCallId")
            if not identity:
                return
            item = self.items.setdefault(
                identity,
                {
                    "id": identity,
                    "type": "toolCall",
                    "provenance": "normalized ACP update",
                },
            )
            item.update(
                {
                    key: update[key]
                    for key in ("status", "content", "rawInput", "rawOutput")
                    if key in update
                }
            )
            if "title" in update:
                item["toolName"] = update["title"]
            item["native"] = {**item.get("native", {}), **update}
            inputs = item.get("rawInput", {})
            command = inputs.get("command") if isinstance(inputs, dict) else None
            if isinstance(command, str):
                item.update(type="commandExecution", command=command)
            if "rawOutput" in update:
                output = update["rawOutput"]
                if isinstance(output, dict) and isinstance(output.get("output"), str):
                    item["aggregatedOutput"] = output["output"]
        if item is not None:
            terminal = item.get("status") in {"completed", "failed"}
            self.append(
                "item/completed" if terminal else "item/updated",
                {
                    "threadId": session_id,
                    "turnId": self.turn_id,
                    "item": dict(item),
                },
            )

    def finish(self, session_id, status, usage=None):
        """Retain terminal ACP usage without guessing cache or reasoning semantics."""
        self.append(
            "acp/promptCompleted",
            {
                "sessionId": session_id,
                "turnId": self.turn_id,
                "status": status,
                "usage": usage,
            },
        )
        for item in self.items.values():
            if item.get("type") in {"agentMessage", "reasoning"}:
                self.append(
                    "item/completed",
                    {
                        "threadId": session_id,
                        "turnId": self.turn_id,
                        "item": dict(item),
                    },
                )
        self.append(
            "turn/completed",
            {
                "threadId": session_id,
                "turn": {"id": self.turn_id, "status": status},
                "identity_source": "host_attempt",
            },
        )
