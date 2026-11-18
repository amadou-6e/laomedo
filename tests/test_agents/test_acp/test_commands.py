"""Current native command discovery invariants; no model acceptance claim."""

import unittest
from unittest.mock import Mock
from acp.schema import AvailableCommandsUpdate

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

    async def test_wrong_session_fails_the_protocol(self):
        """Foreign advertisements cannot become a usable catalog."""
        await self.advertise([{"name": "status", "description": "Status"}], "foreign")
        self.assertTrue(self.session.protocol_failed)
        self.assertIsNone(self.session.command_catalog())

    async def test_invalid_metadata_withdraws_catalog_without_breaking_chat(self):
        """Optional discovery failure preserves raw updates and ordinary turns."""
        await self.advertise([{"name": "status", "description": "Status"}])
        self.session.on_update = Mock()
        await self.advertise([{"name": "status", "description": "x" * 4001}])
        self.assertFalse(self.session.protocol_failed)
        self.assertIsNone(self.session.command_catalog())
        self.assertEqual(len(self.session.updates), 2)
        self.session.on_update.assert_called_once()

    async def test_real_sdk_aliases_are_observed(self):
        """Parse the pinned SDK's actual notification rather than a mock shape."""
        update = AvailableCommandsUpdate.model_validate(
            {
                "sessionUpdate": "available_commands_update",
                "availableCommands": [
                    {
                        "name": "review",
                        "description": "Review",
                        "input": {"hint": "instructions"},
                    }
                ],
            }
        )
        await self.session.session_update("owned", update)
        self.assertFalse(self.session.protocol_failed)
        self.assertEqual(
            self.session.command_catalog().commands[0].input.hint, "instructions"
        )
