"""Internal transport configuration controls; no provider requests or credentials."""

import os
import unittest
from unittest.mock import patch

from laomedo.agents.agents.codex.controller.settings import Settings
from laomedo.agents.errors import RunnerError


class TransportSettingsTests(unittest.TestCase):
    def test_invalid_environment_is_mapped_to_the_safe_public_code(self):
        for name in (
            "LAOMEDO_CODEX_STREAM_MAX_BYTES",
            "LAOMEDO_CODEX_STREAM_STARTUP_MARGIN",
        ):
            for value in ("", "0", "-1", "nan", "inf", "private-invalid-value"):
                with (
                    self.subTest(name=name, value=value),
                    patch.dict(os.environ, {name: value}, clear=True),
                ):
                    with self.assertRaises(RunnerError) as failure:
                        Settings.load()
                    self.assertEqual(
                        failure.exception.code, "runner_transport_configuration_invalid"
                    )
                    self.assertEqual(
                        failure.exception.args,
                        ("runner_transport_configuration_invalid",),
                    )
                    self.assertNotIn(value or "private", repr(failure.exception))
