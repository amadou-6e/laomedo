"""Internal command-event transports for completion and cleanup controls."""

import json

from test_agents.test_runtime.transport import FakeServer
from laomedo.agents.agents.base.acp.models import NativeCommandCatalog
from laomedo.agents.agents.codex.controller.models import CodexCommandResult


class CommandTransport(FakeServer):
    def __init__(self, *args, events):
        super().__init__(*args)
        self.command_events = events

    def wait_turn(self, turn_id, timeout, cancelled):
        status = super().wait_turn(turn_id, timeout, cancelled)
        self.events.extend(self.command_events)
        for event in self.command_events:
            self.log.write(json.dumps(event) + "\n")
        self.log.flush()
        return status


class InitialStatusTransport(FakeServer):
    """Control-only first status, followed by an ordinary same-thread continuation."""

    async def open(self, record, *, resume, reuse=False):
        if reuse:
            assert resume and self.active_thread_id == record["thread_id"]
            return self.active_thread_id
        return await super().open(record, resume=resume)

    def check_health(self, *, idle=False):
        if getattr(self, "authorization_probe", None) and not self.authorization_probe(
            idle=idle
        ):
            from laomedo.agents.errors import RunnerError

            raise RunnerError(self.authorization_failure["code"])
        return None

    def command_catalog(self):
        return NativeCommandCatalog(
            commands=[{"name": "status", "description": "Status"}]
        )

    async def prompt(self, text, *, skills, seconds, cancelled, command=None):
        if command is not None:
            assert text == "/status" and command.name == "status"
            assert command.catalog_revision == self.command_catalog().revision()
            return CodexCommandResult(
                command="status",
                stop_reason="end_turn",
                status="completed",
                answer="Model: test-model\nThread: native-thread",
            )
        return await super().prompt(
            text, skills=skills, seconds=seconds, cancelled=cancelled
        )

    def wait_turn(self, turn_id, timeout, cancelled):
        if self.resume:
            (self.evidence / "workspace/agent.txt").write_text("from-first-turn")
        return super().wait_turn(turn_id, timeout, cancelled)


class UncertainCleanupTransport(FakeServer):
    def wait_turn(self, turn_id, timeout, cancelled):
        super().wait_turn(turn_id, timeout, cancelled)
        self.events.append(
            {
                "method": "item/started",
                "params": {
                    "turnId": turn_id,
                    "item": {"type": "commandExecution", "id": "exec-1"},
                },
            }
        )
        return "completed", None

    async def close(self):
        await super().close()
        raise OSError("synthetic cleanup failure")


class ResumeCommandTransport(FakeServer):
    def wait_turn(self, turn_id, timeout, cancelled):
        super().wait_turn(turn_id, timeout, cancelled)
        self.events.append(
            {
                "method": "item/started",
                "params": {
                    "turnId": turn_id,
                    "item": {"type": "commandExecution", "id": "exec-1"},
                },
            }
        )
        return "completed", None
