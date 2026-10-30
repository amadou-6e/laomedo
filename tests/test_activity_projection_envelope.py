"""Internal old-writer byte controls; these do not establish live acceptance."""

import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import unittest

from pydantic import ValidationError

from laomedo.agents.activity.models import ActivityProjection
from laomedo.agents.activity.projection import project
from laomedo.agents.agents.opencode.activity.projection import (
    project as project_opencode,
)


class ActivityProjectionEnvelopeTests(unittest.TestCase):
    """Pin wire compatibility independently of the new envelope constructor."""

    @classmethod
    def setUpClass(cls):
        """Read outputs captured from Git-pinned projectors before source edits."""
        cls.contract = json.loads(
            (
                Path(__file__).parent / "contracts/activity-projection-3508b7aee.json"
            ).read_text(encoding="utf-8")
        )

    def test_projectors_match_frozen_old_writer_bytes(self):
        """Require exact keys, omission, Unicode escaping and nested JSON bytes."""
        self.assertEqual(
            self.contract["base"], "3508b7aee627053e21369cc08a16f15520345374"
        )
        self.assertIn("not_live_acceptance", self.contract["evidence_kind"])
        self.assertEqual(len(self.contract["sources"]), 5)
        for case in self.contract["cases"]:
            with self.subTest(case=case["name"]):
                writer = project if case["projector"] == "shared" else project_opencode
                actual = writer(case["events"], **case["kwargs"])
                expected = base64.b64decode(case["json_base64"])
                self.assertEqual(hashlib.sha256(expected).hexdigest(), case["sha256"])
                self.assertEqual(list(actual), case["keys"])
                self.assertEqual(json.dumps(actual).encode("utf-8"), expected)

    def test_observations_keep_identity_and_partial_unknown_values(self):
        """Do not copy, coerce or validate existing external native snapshots."""
        payload = project([], root_thread="root")
        payload.update(
            turns=[{"extension": {"opaque": [None, "native-marker"]}}],
            items=[{"arbitrary": "native-marker"}],
            threads=[{"future": True}],
            diagnostics=[{"native": "native-marker"}],
            telemetry=[{"attributes": {"future": [1, None]}}],
            usage={"inputTokens": 3},
            usage_by_thread={"root": None, "partial": {"inputTokens": 3}},
            usage_points=[{"usage": None, "extension": "native-marker"}],
            cost={"amount": None, "future": {"native": "native-marker"}},
        )
        envelope = ActivityProjection(**payload)
        for output in (envelope.to_payload(), envelope.to_usage_first_payload()):
            for field in (
                "turns",
                "items",
                "threads",
                "diagnostics",
                "telemetry",
                "usage",
                "usage_by_thread",
                "usage_points",
                "cost",
            ):
                self.assertIs(getattr(envelope, field), payload[field])
                self.assertIs(output[field], payload[field])
            self.assertEqual(output["usage"], {"inputTokens": 3})
            self.assertIsNone(output["usage_by_thread"]["root"])
        self.assertNotIn("native-marker", repr(envelope))

    def test_diagnostics_omission_empty_and_null_are_distinct(self):
        """Preserve each supported field-presence state in both wire layouts."""
        payload = project_opencode([])
        self.assertNotIn("diagnostics", payload)
        for extra in ({}, {"diagnostics": []}, {"diagnostics": None}):
            with self.subTest(extra=extra):
                envelope = ActivityProjection(**payload, **extra)
                for output in (
                    envelope.to_payload(),
                    envelope.to_usage_first_payload(),
                ):
                    self.assertEqual("diagnostics" in output, "diagnostics" in extra)
                    if extra:
                        self.assertIs(output["diagnostics"], extra["diagnostics"])

    def test_native_depth_and_extension_values_are_not_new_validation_boundaries(self):
        """Nested observed JSON must not acquire Pydantic's recursion limits."""
        native = {}
        cursor = native
        for _ in range(300):
            cursor["nested"] = {}
            cursor = cursor["nested"]
        payload = project([])
        payload["telemetry"] = [{"attributes": native}]
        envelope = ActivityProjection(**payload)
        self.assertIs(envelope.to_payload()["telemetry"][0]["attributes"], native)

    def test_application_metadata_remains_strict(self):
        """No string/int/bool coercion or new unrecognized envelope fields."""
        for field, invalid in (
            ("clock", 1),
            ("cost_reason", None),
            ("telemetry_coverage", []),
            ("uncorrelated_thread_count", True),
            ("unknown", "value"),
        ):
            with self.subTest(field=field):
                payload = project([])
                payload[field] = invalid
                with self.assertRaises(ValidationError):
                    ActivityProjection(**payload)

    def test_import_orders_in_fresh_processes(self):
        """Exercise actual installed dependencies without fake module scaffolds."""
        modules = [
            "laomedo.agents.activity.models",
            "laomedo.agents.activity.store",
            "laomedo.agents.activity.projection",
            "laomedo.agents.agents.opencode.activity.projection",
        ]
        for offset in range(len(modules)):
            order = modules[offset:] + modules[:offset]
            with self.subTest(first=order[0]):
                result = subprocess.run(
                    [
                        sys.executable,
                        "-c",
                        "; ".join(f"import {name}" for name in order),
                    ],
                    capture_output=True,
                    text=True,
                    timeout=90,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
