"""Protect the private native configuration boundary; not live Agent acceptance."""

import unittest

from pydantic import ValidationError

from laomedo.agents.agents.opencode.models import OpenCodeConfig


class OpenCodeConfigTests(unittest.TestCase):
    """Verify redaction and admitted-input ownership at the native projection."""

    def test_capability_only_appears_at_the_private_native_boundary(self):
        """Normal diagnostics/dumps hide the capability required by the native MCP client."""
        capability = "internal-configuration-test-capability"
        config = OpenCodeConfig(
            permissions={"*": "deny", "skill": {"review": "allow"}},
            broker_port=12345,
            broker_token=capability,
        )
        self.assertNotIn(capability, repr(config))
        self.assertNotIn(capability, config.model_dump_json())
        native = config.to_config()
        endpoint = native["mcp"]["laomedo"]
        self.assertEqual(endpoint["url"], "http://host.docker.internal:12345/mcp")
        self.assertEqual(endpoint["headers"], {"Authorization": "Bearer " + capability})
        native["permission"]["skill"]["review"] = "deny"
        self.assertEqual(config.permissions["skill"]["review"], "allow")

    def test_invalid_inputs_do_not_echo_the_private_capability(self):
        """Reject invalid internal launch values without exposing the supplied secret."""
        capability = "internal-invalid-configuration-capability"
        with self.assertRaises(ValidationError) as failure:
            OpenCodeConfig(
                permissions={"*": "unsupported"},
                broker_port=0,
                broker_token=capability,
            )
        self.assertNotIn(capability, str(failure.exception))


if __name__ == "__main__":
    unittest.main()
