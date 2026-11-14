"""In-memory peers for internal ACP wire ordering; no provider is executed."""

import json
import queue
from types import SimpleNamespace


class NotificationWire:
    """Reply to setup and deliver terminal evidence before prompt completion."""

    def __init__(self):
        self.messages = queue.Queue()
        self.prompt_id = None

    def emit(self, message):
        self.messages.put(
            SimpleNamespace(channel="stdout", data=json.dumps(message).encode())
        )

    def write(self, payload):
        request = json.loads(payload)
        method = request.get("method")
        if method is None:
            self.on_reply(request)
            return
        if method == "initialize":
            result = {
                "protocolVersion": 1,
                "agentCapabilities": {"loadSession": True},
            }
        elif method == "session/new":
            result = {"sessionId": "native-session"}
        elif method == "session/prompt":
            self.prompt_id = request["id"]
            self.on_prompt()
            return
        else:
            raise AssertionError(method)
        self.emit({"id": request["id"], "result": result})

    def on_prompt(self):
        self.emit(
            {
                "method": "_laomedo/codexEvent",
                "params": {
                    "method": "turn/completed",
                    "params": {
                        "threadId": "native-session",
                        "turn": {"id": "actual-native-turn", "status": "completed"},
                    },
                },
            }
        )
        self.emit({"id": self.prompt_id, "result": {"stopReason": "end_turn"}})

    def on_reply(self, message):
        raise AssertionError("Unexpected host response")

    def read_line(self):
        return self.messages.get(timeout=5)

    def close(self):
        self.messages.put(None)


class PrecheckWire(NotificationWire):
    """Complete a pending prompt only after the real SDK routes its precheck."""

    def __init__(self):
        super().__init__()
        self.precheck_reply = None

    def on_prompt(self):
        self.emit(
            {
                "id": "precheck-request",
                "method": "_laomedo/outputPrecheck",
                "params": {"threadId": "native-session", "callId": "native-call"},
            }
        )

    def on_reply(self, message):
        if message.get("id") != "precheck-request" or "error" in message:
            raise AssertionError("Precheck was not answered successfully")
        self.precheck_reply = message["result"]
        self.emit({"id": self.prompt_id, "result": {"stopReason": "end_turn"}})
