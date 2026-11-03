"""Preserve serialized contracts, authority boundaries and unknown outcomes."""

from support.paths import repository_root
import json
from contextlib import closing, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from laomedo.work_graph.github import import_pages
from laomedo.work_graph.launch import preflight


class WorkGraphRecordTests(unittest.TestCase):
    def test_work_grant_cli_flat_shape_and_redeemed_payload_match_old_writers(self):
        from laomedo.work_graph.__main__ import main
        from laomedo.work_graph.grants import LocalGrantAuthority, LaunchError
        from test_work_graph.utils import make_snapshot

        WORK = "github:S-20"

        frozen = make_snapshot()
        with TemporaryDirectory() as temporary:
            snapshot = frozen.save(Path(temporary) / "snapshots")
            path = Path(temporary) / "grants.sqlite"
            output = StringIO()
            args = [
                "issue-grant",
                str(snapshot),
                "--work-key",
                WORK,
                "--grant-store",
                str(path),
                "--timeout-seconds",
                "30",
                "--max-turns",
                "0",
            ]
            with (
                patch("sys.stdin") as stdin,
                patch("builtins.input", return_value=WORK),
                redirect_stdout(output),
            ):
                stdin.isatty.return_value = True
                self.assertEqual(main(args), 0)
            receipt = json.loads(output.getvalue())
            self.assertEqual(
                set(receipt),
                {
                    "grant_ref",
                    "work_key",
                    "graph_snapshot_id",
                    "content_digest",
                    "expires_at",
                    "timeout_seconds",
                    "max_turns",
                },
            )
            self.assertEqual(
                (
                    receipt["work_key"],
                    receipt["timeout_seconds"],
                    receipt["max_turns"],
                ),
                (WORK, 30, 0),
            )
            authority = LocalGrantAuthority(path)
            binding = preflight(frozen, frozen, WORK)
            redeemed = authority(receipt["grant_ref"], binding)
            self.assertEqual(
                redeemed,
                dict(
                    grant_id=receipt["grant_ref"],
                    operator_authorized=True,
                    work_key=WORK,
                    graph_snapshot_id=receipt["graph_snapshot_id"],
                    content_digest=receipt["content_digest"],
                    runner="langflow-local",
                    scope="stage-launch",
                    expires_at=receipt["expires_at"],
                    limits={"timeout_seconds": 30, "max_turns": 0},
                ),
            )
            self.assertNotIn("operator_id", redeemed)
            with self.assertRaisesRegex(LaunchError, "^grant_invalid$"):
                authority(receipt["grant_ref"], binding)
            ref = authority.issue(
                work_key=WORK,
                graph_snapshot=frozen,
                expires_at=(
                    datetime.now(timezone.utc) + timedelta(minutes=5)
                ).isoformat(),
                timeout_seconds=30,
                max_turns=0,
            )
            with closing(authority._connect()) as db, db:
                db.execute(
                    "UPDATE grants SET expires_at=? WHERE grant_id=?",
                    ("2000-01-01T00:00:00+00:00", ref),
                )
            with self.assertRaisesRegex(LaunchError, "^grant_expired$"):
                authority(ref, binding)
            with closing(authority._connect()) as db:
                self.assertIsNone(
                    db.execute(
                        "SELECT redeemed_at FROM grants WHERE grant_id=?", (ref,)
                    ).fetchone()[0]
                )

    def test_work_launch_summary_preserves_unknown_completion_without_output_leak(self):
        from unittest.mock import Mock
        from laomedo.work_graph.local_launch import launch_local_saved_flow

        record = dict(
            run_id="run",
            trace_id="trace",
            status="external_outcome_unknown",
            completion_basis=None,
            evidence_complete=0,
            dispatch_attempts=1,
            graph_revision="sha256:graph",
        )
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = root / "snapshot.json"
            snapshot.write_text("{}", encoding="utf-8")
            for output in ("private-output", "", None):
                with (
                    self.subTest(output_present=bool(output)),
                    patch(
                        "laomedo.work_graph.models.GraphSnapshot.from_dict",
                        return_value=object(),
                    ),
                    patch(
                        "laomedo.work_graph.local_launch.LocalGrantAuthority",
                        return_value=Mock(path=root / "grants.sqlite"),
                    ),
                    patch(
                        "laomedo.work_graph.local_launch._private_path",
                        return_value=root / "runs.sqlite",
                    ),
                    patch("laomedo.work_graph.local_launch.WorkflowRunStore"),
                    patch("laomedo.work_graph.client.LangflowLocalClient"),
                    patch(
                        "laomedo.work_graph.local_launch.launch_github_docker_saved_flow_stage",
                        return_value=(record, output),
                    ),
                ):
                    summary = launch_local_saved_flow(
                        snapshot_path=snapshot,
                        work_key="github:S-20",
                        flow_id="flow",
                        langflow_base="http://127.0.0.1:8000",
                        grant_store=root / "grants.sqlite",
                        grant_ref="grant",
                        run_store=root / "runs.sqlite",
                        task="task",
                    )
                self.assertEqual(
                    summary,
                    {
                        **record,
                        "evidence_complete": False,
                        "output_present": bool(output),
                    },
                )
                self.assertEqual(
                    list(summary),
                    [
                        "run_id",
                        "trace_id",
                        "status",
                        "completion_basis",
                        "evidence_complete",
                        "dispatch_attempts",
                        "output_present",
                        "graph_revision",
                    ],
                )
                self.assertNotIn("private-output", json.dumps(summary))

    def test_work_launch_preimages_match_captured_old_writer(self):
        repo = repository_root()
        corpus = json.loads(
            (repo / "tests/test_work_graph/fixtures/corpus.json").read_text(
                encoding="utf-8"
            )
        )
        graph = import_pages(
            "verify/exp16", corpus["base"], fetched_at="2026-10-05T10:00:00+00:00"
        )
        expected = json.loads(
            (
                repository_root() / "tests/test_work_graph/fixtures/launch-record.json"
            ).read_text(encoding="utf-8")
        )
        self.assertEqual(preflight(graph, graph, "github:S-20"), expected)
