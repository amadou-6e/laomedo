"""Local-only preflight for the frozen S7 Docker probe."""

import ast
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import runpy
import sys
import types
from unittest.mock import patch

from laomedo.host.publication.bundle.errors import BundleStageError
from laomedo.host.publication.bundle.settings import PINNED_IMAGE_ID
from laomedo.host.publication.bundle.stage import _read_frozen
from laomedo.host.publication.bundle.stage import verify_frozen_bundle

PROBE_PATH = (
    Path(__file__).resolve().parents[1] / "experiments" / "exp100" / "probe_stage_s7.py"
)
ROOT = PROBE_PATH.parents[2]
CONTRACT = json.loads(
    (ROOT / "tools/migrations/retained-ingestion-callers.json").read_text()
)
EXPECTED = next(
    item["sha256"]
    for item in CONTRACT["files"]
    if item["path"] == PROBE_PATH.relative_to(ROOT).as_posix()
)
assert hashlib.sha256(PROBE_PATH.read_bytes()).hexdigest() == EXPECTED
sys.path.insert(0, str(ROOT / "tools/migrations"))
MIGRATION = runpy.run_path(str(ROOT / "tools/migrations/migrate_module_paths.py"))
SOURCE = PROBE_PATH.read_text(encoding="utf-8")
MIGRATED = MIGRATION["migrate_source"](SOURCE)
# A retained protocol fixture is adapted only in memory for internal controls.
# Its source bytes remain historical evidence; no model or Docker run occurs.
assert ast.dump(
    ast.Module(
        body=[
            node
            for node in ast.parse(SOURCE).body
            if not isinstance(node, (ast.Import, ast.ImportFrom))
        ],
        type_ignores=[],
    )
) == ast.dump(
    ast.Module(
        body=[
            node
            for node in ast.parse(MIGRATED).body
            if not isinstance(node, (ast.Import, ast.ImportFrom))
        ],
        type_ignores=[],
    )
)
probe_stage_s7 = types.ModuleType("exp100_stage_s7")
probe_stage_s7.__file__ = str(PROBE_PATH)
exec(compile(MIGRATED, str(PROBE_PATH), "exec"), probe_stage_s7.__dict__)
fixture = probe_stage_s7.fixture


class ProbeS7Preflight(unittest.TestCase):
    def test_unknown_positive_preserves_case_without_key_error(self):
        observation = {"status": "unknown"}
        checkpoints = []

        def checkpoint():
            checkpoints.append(observation["cases"].copy())

        with (
            patch.object(
                probe_stage_s7,
                "verify_frozen_bundle",
                return_value={"status": "unknown"},
            ),
            patch.object(probe_stage_s7, "_run") as inspect,
        ):
            inspect.return_value.returncode = 1
            probe_stage_s7.run_once(observation, checkpoint)
        self.assertEqual(observation["status"], "failed")
        self.assertEqual(
            observation["cases"]["positive"]["result"], {"status": "unknown"}
        )
        self.assertGreaterEqual(len(checkpoints), 2)

    def test_two_synthetic_fixtures_and_wrong_commit_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            positive = fixture(root, "positive")
            negative = fixture(root, "wrong-commit")
            self.assertNotEqual(positive["commit"], positive["baseline"])
            self.assertNotEqual(negative["commit"], negative["baseline"])
            self.assertNotEqual(positive["run_id"], negative["run_id"])
            attempt, frozen = _read_frozen(
                positive["runner"],
                positive["private"],
                positive["run_id"],
                positive["attempt_id"],
            )
            self.assertTrue(attempt.is_dir())
            self.assertEqual(frozen["advertised_commit"], positive["commit"])
            calls = []

            def no_docker(*args, **kwargs):
                calls.append((args, kwargs))
                raise AssertionError("negative case reached Docker")

            with self.assertRaisesRegex(BundleStageError, "candidate_commit_mismatch"):
                verify_frozen_bundle(
                    negative["runner"],
                    negative["private"],
                    run_id=negative["run_id"],
                    attempt_id=negative["attempt_id"],
                    baseline_bundle=negative["baseline_bundle"],
                    expected_baseline_sha256=negative["baseline_sha256"],
                    commit=negative["baseline"],
                    image_id=PINNED_IMAGE_ID,
                    docker=no_docker,
                )
            self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
