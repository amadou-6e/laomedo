"""Freeze refusal, uncertain outcome and safe diagnostic projection contracts."""

import ast
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from laomedo.host.mediation.store import MediationStore
from laomedo.host.publication.ingestion.errors import BundleIngestError
from support.paths import repository_root


class PublicationErrorBoundaryTests(unittest.TestCase):
    REFUSALS = (
        "bundle_not_regular",
        "bundle_size_or_type",
        "bundle_changed_or_oversized",
        "bundle_unreadable",
    )
    INTERNAL = (
        "attempt_already_reserved",
        "attempt_identity_invalid",
        "attempt_unreconciled",
        "run_binding_invalid",
        "run_identity_invalid",
        "run_transfer_busy_or_unreconciled",
        "stage_boundary_invalid",
        "freeze_request_invalid",
        "run_grant_mismatch",
        "run_changed_during_freeze",
    )

    def test_freezer_refusals_and_raised_diagnostics_keep_distinct_outcomes(self):
        with tempfile.TemporaryDirectory() as directory:
            freezer = Mock()
            store = MediationStore(
                Path(directory) / "effects.sqlite",
                now=lambda: 1000,
                monotonic=lambda: 100,
                stage_freezer=freezer,
            )
            _, token = store.issue(
                run_id="run-a",
                invocation_id="inv-a",
                repository="example/disposable",
                branch="run-branch",
                operations={"git_push"},
                ttl_seconds=60,
            )
            transport = Mock(
                side_effect=AssertionError("Provider dispatch is forbidden")
            )
            for code in self.REFUSALS:
                freezer.return_value = {"status": "refused", "reason": code}
                self.assertEqual(
                    store.invoke(
                        token=token,
                        repository="example/disposable",
                        operation="bundle_freeze",
                        payload={"attempt_id": "attempt-a"},
                        effect_id=None,
                        transport=transport,
                    ),
                    {"state": "rejected", "error": code},
                )
            for error in [
                BundleIngestError(code) for code in (*self.REFUSALS, *self.INTERNAL)
            ] + [RuntimeError("private-source-and-token")]:
                freezer.side_effect = error
                result = store.invoke(
                    token=token,
                    repository="example/disposable",
                    operation="bundle_freeze",
                    payload={"attempt_id": "attempt-a"},
                    effect_id=None,
                    transport=transport,
                )
                self.assertEqual(result, {"state": "unknown", "resent": False})
                self.assertNotIn("private", json.dumps(result))
            transport.assert_not_called()

    def test_exported_refusals_are_descriptively_catalogued(self):
        root = repository_root()
        catalogue = json.loads(
            (
                root / "frontend/langflow-skill-viewer/errors/node-error-catalog.json"
            ).read_text(encoding="utf-8")
        )
        for code in self.REFUSALS:
            for field in ("title", "description", "recovery"):
                self.assertTrue(catalogue[code][field].strip(), (code, field))
        codes = set()
        for relative in ("ingestion/utils.py", "verified/utils.py"):
            tree = ast.parse(
                (root / "src/laomedo/host/publication" / relative).read_text(
                    encoding="utf-8"
                )
            )
            codes.update(
                node.exc.args[0].value
                for node in ast.walk(tree)
                if isinstance(node, ast.Raise)
                and isinstance(node.exc, ast.Call)
                and isinstance(node.exc.func, ast.Name)
                and node.exc.func.id == "BundleIngestError"
                and node.exc.args
                and isinstance(node.exc.args[0], ast.Constant)
            )
        self.assertEqual(codes, set(self.REFUSALS) | set(self.INTERNAL))
