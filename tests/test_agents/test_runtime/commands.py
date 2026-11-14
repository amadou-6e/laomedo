"""Internal command-event transports for completion and cleanup controls."""

import json

from test_agents.test_runtime.transport import FakeServer


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
