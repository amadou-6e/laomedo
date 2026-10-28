"""Own native app-server processes and the split-controller boundary."""

from __future__ import annotations

import json
import queue
import threading
import time
from abc import ABC, abstractmethod

import laomedo.agents.contracts.output as _contracts_output
import laomedo.agents.runtime.errors as _runtime_errors


class BaseNativeServer(ABC):
    """Codex JSON-RPC, event recording and turn control independent of Docker I/O."""

    def _redact(self, line: str) -> str:
        for secret in self.secret_redactions:
            line = line.replace(secret, "[REDACTED_RUN_CAPABILITY]")
        return line

    def request(self, method: str, params: dict, timeout: float = 30) -> dict:
        self.seq += 1
        request_id = self.seq
        self._write(
            json.dumps({"id": request_id, "method": method, "params": params}) + "\n"
        )
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                msg = self.messages.get(timeout=min(0.5, deadline - time.monotonic()))
            except queue.Empty:
                if self._transport_exited():
                    raise _runtime_errors.RunnerError("app_server_exited")
                continue
            if msg.get("id") == request_id and "method" not in msg:
                return msg
            self._observe(msg)
        raise _runtime_errors.RunnerError("request_timeout:" + method)

    def notify(self, method: str, params: dict) -> None:
        self._write(json.dumps({"method": method, "params": params}) + "\n")

    def _observe(self, msg):
        self.events.append(msg)
        reference = getattr(self, "output_requirements", None)
        if (
            reference is not None
            and msg.get("method") == "item/tool/call"
            and "id" in msg
        ):
            params = msg.get("params") or {}
            response = _contracts_output.precheck_response(
                reference, params, self.active_thread_id
            )
            if (
                params.get("tool") == "laomedo_output_precheck"
                and params.get("namespace") is None
                and params.get("threadId") == self.active_thread_id
            ):
                self.precheck_call_count = getattr(self, "precheck_call_count", 0) + 1
                result = json.loads(response["contentItems"][0]["text"])
                if not any(
                    error["code"] == "precheck_binding_mismatch"
                    for error in result["errors"]
                ):
                    calls = getattr(self, "verified_precheck_calls", set())
                    if isinstance(params.get("callId"), str):
                        calls.add(params["callId"])
                    self.verified_precheck_calls = calls
            self._write(json.dumps({"id": msg["id"], "result": response}) + "\n")

    def wait_turn(
        self, turn_id: str, timeout: float, cancelled: threading.Event
    ) -> tuple[str, str | None]:
        deadline = time.monotonic() + timeout
        cursor = 0
        interrupt_sent = False
        while time.monotonic() < deadline:
            for event in self.events[cursor:]:
                if event.get("method") == "turn/completed":
                    turn = event.get("params", {}).get("turn") or {}
                    if turn.get("id") == turn_id:
                        self.native_completion_status = turn.get("status") or "unknown"
                        if (
                            interrupt_sent
                            and self.native_completion_status == "interrupted"
                        ):
                            return "cancelled", "cancelled_by_user"
                        return self.native_completion_status, None
            cursor = len(self.events)
            if cancelled.is_set() and not interrupt_sent:
                self.interrupt(turn_id)
                interrupt_sent = True
                deadline = min(deadline, time.monotonic() + 5)
            try:
                msg = self.messages.get(timeout=min(0.25, deadline - time.monotonic()))
            except queue.Empty:
                if self._transport_exited():
                    return (
                        ("cancelled", "cancel_native_unconfirmed")
                        if interrupt_sent
                        else ("failed", "app_server_exited")
                    )
                continue
            self._observe(msg)
        if interrupt_sent:
            return "cancelled", "cancel_native_unconfirmed"
        self.interrupt(turn_id)
        return "timeout", "turn_timeout"

    def interrupt(self, turn_id: str) -> None:
        if not self.active_thread_id:
            return
        try:
            response = self.request(
                "turn/interrupt",
                {"threadId": self.active_thread_id, "turnId": turn_id},
                timeout=5,
            )
            self.interrupt_acknowledged = (
                "result" in response and "error" not in response
            )
        except (_runtime_errors.RunnerError, OSError, ValueError):
            # Forced container removal below remains the authoritative boundary.
            self.interrupt_acknowledged = False

    @abstractmethod
    def _write(self, data: str) -> None:
        """Send complete native request text through the concrete transport."""
        raise NotImplementedError("A concrete native transport must send requests")

    @abstractmethod
    def _transport_exited(self) -> bool:
        """Return confirmed termination or raise on an uncertain transport outcome."""
        raise NotImplementedError(
            "A concrete native transport must confirm termination"
        )
