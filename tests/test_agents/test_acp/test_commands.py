"""Current native command discovery invariants; no model acceptance claim."""

import unittest
from unittest.mock import Mock

from laomedo.agents.agents.base.acp.session import AcpSession


class NativeCommandTests(unittest.IsolatedAsyncioTestCase):
    """Check session identity, replacement semantics and detached observations."""

    def setUp(self):
        """Create a callback receiver without opening Docker or a protocol pipe."""
        self.session = AcpSession.__new__(AcpSession)
        self.session.session_id = "owned"
        self.session.updates = []
        self.session._commands = None
        self.session.on_update = None
        self.session.protocol_failed = False

    async def advertise(self, commands, identity="owned"):
        """Deliver the SDK callback's serialized command update."""
        update = Mock()
        update.model_dump.return_value = {
            "sessionUpdate": "available_commands_update",
            "availableCommands": commands,
        }
        await self.session.session_update(identity, update)

    async def test_catalog_survives_turn_buffer_clear_and_is_detached(self):
        """Clearing activity never loses discovered commands or leaks mutable state."""
        self.assertIsNone(self.session.command_catalog())
        await self.advertise(
            [
                {
                    "name": "review",
                    "description": "Review changes",
                    "input": {"hint": "instructions"},
                }
            ]
        )
        observed = self.session.command_catalog()
        digest = observed.revision()
        self.session.updates.clear()
        observed.commands.clear()
        self.assertEqual(self.session.command_catalog().commands[0].name, "review")
        self.assertEqual(self.session.command_catalog().revision(), digest)
        await self.advertise([])
        self.assertEqual(self.session.command_catalog().commands, [])
        self.assertNotEqual(self.session.command_catalog().revision(), digest)

    async def test_wrong_session_and_unbounded_metadata_fail_closed(self):
        """Foreign or malformed advertisements cannot become a usable catalog."""
        await self.advertise([{"name": "status", "description": "Status"}], "foreign")
        self.assertTrue(self.session.protocol_failed)
        self.assertIsNone(self.session.command_catalog())
        self.session.protocol_failed = False
        await self.advertise([{"name": "status", "description": "x" * 4001}])
        self.assertTrue(self.session.protocol_failed)
        self.assertIsNone(self.session.command_catalog())
