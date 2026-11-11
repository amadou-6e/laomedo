"""Rollout export binds reads to recorded resources and publishes only verified history."""

from importlib.util import find_spec
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from laomedo.agents.errors import RunnerError
from laomedo.agents.agents.codex.activity.rollout_export import export_rollout


class RolloutCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name) / "private-state"
        self.run_id = "b305a7bd-0ea9-40eb-b4ef-34dbef4fd4a4"
        self.thread = "c61de4af-35cc-4e25-9dd6-73cc9acdf9d5"
        self.run_dir = self.state / "runs" / self.run_id
        self.run_dir.mkdir(parents=True)
        self.image = "sha256:" + "a" * 64
        self.record = {
            "run_id": self.run_id,
            "thread_id": self.thread,
            "image_id": self.image,
            "profile": "laomedo-isolated-history",
            "container_ownership": {"docker_endpoint": "unix:///recorded.sock"},
        }
        self.save()

    def save(self):
        (self.run_dir / "record.json").write_text(json.dumps(self.record))


class BindingTests(RolloutCase):
    def test_missing_or_invalid_binding_refused_before_docker_access(self):
        for field, value in [
            ("container_ownership", None),
            ("container_ownership", {}),
            ("container_ownership", {"docker_endpoint": ""}),
            ("profile", None),
            ("profile", "/some/host/path"),
            ("image_id", "mutable:latest"),
            ("image_id", None),
        ]:
            with self.subTest(field=field, value=value):
                original = self.record[field]
                self.record[field] = value
                self.save()
                with patch(
                    "laomedo.agents.agents.codex.activity.rollout_export.DockerRuntime"
                ) as runtime:
                    with self.assertRaisesRegex(
                        RunnerError, "native_rollout_binding_invalid"
                    ):
                        export_rollout(self.state, self.run_id)
                    runtime.assert_not_called()
                self.record[field] = original

    def test_invalid_thread_refused_before_docker_access(self):
        self.record["thread_id"] = "not-a-thread"
        self.save()
        with patch(
            "laomedo.agents.agents.codex.activity.rollout_export.DockerRuntime"
        ) as runtime:
            with self.assertRaisesRegex(RunnerError, "invalid_native_thread_id"):
                export_rollout(self.state, self.run_id)
            runtime.assert_not_called()


@unittest.skipUnless(find_spec("py_docker"), "Requires optional runner dependencies")
class ExportTests(RolloutCase):
    def setUp(self):
        super().setUp()
        from py_docker.execution.models import CommandResult

        self.payload = (
            json.dumps({"type": "session_meta", "payload": {"id": self.thread}}) + "\n"
        ).encode()
        self.path = (
            "/home/runner/.codex/sessions/2026/10/01/rollout-" + self.thread + ".jsonl"
        )
        self.outputs = [
            (self.path + "\n").encode(),
            str(len(self.payload)).encode(),
            self.payload,
        ]
        self.results = CommandResult
        self.jobs = []
        runtime_patch = patch(
            "laomedo.agents.agents.codex.activity.rollout_export.DockerRuntime"
        )
        self.runtime = runtime_patch.start()
        self.addCleanup(runtime_patch.stop)
        self.client = (
            self.runtime.return_value.client.return_value.__enter__.return_value
        )
        self.client.volumes.exists.return_value = True
        self.runtime.execute_job.side_effect = self.execute

    def execute(self, client, job):
        self.assertIs(client, self.client)
        self.jobs.append(job)
        return self.results(
            exit_code=0, stdout=self.outputs[len(self.jobs) - 1], stderr=b""
        )

    def test_exact_session_policy_recorded_binding_and_bounded_reads(self):
        output = export_rollout(self.state, self.run_id)
        self.assertEqual(output.read_bytes(), self.payload)
        self.runtime.assert_called_once_with({"DOCKER_HOST": "unix:///recorded.sock"})
        self.client.images.resolve.assert_called_once_with(
            self.image, expected_id=self.image
        )
        self.client.volumes.exists.assert_called_once_with(self.record["profile"])
        self.assertEqual(len(self.jobs), 3)
        self.assertEqual(
            [job.spec.entrypoint for job in self.jobs], [["find"], ["stat"], ["cat"]]
        )
        self.assertEqual(
            [job.limits.max_bytes for job in self.jobs],
            [2 * 1024 * 1024, 4096, len(self.payload)],
        )
        for job in self.jobs:
            self.assertEqual(job.spec.image, self.image)
            self.assertEqual(job.spec.network_mode, "none")
            self.assertTrue(job.spec.read_only)
            self.assertEqual(job.spec.user, "10001:10001")
            self.assertEqual(job.spec.mounts[0].source, self.record["profile"])
            self.assertTrue(job.spec.mounts[0].read_only)
            self.assertEqual(job.receipt_path.parent, self.run_dir / "rollout-receipts")
            self.assertEqual(job.limits.seconds, 30)
        self.assertIn("-links", self.jobs[0].spec.command)
        self.assertEqual(len({job.receipt_path for job in self.jobs}), 3)
        self.client.images.build.assert_not_called()
        self.client.volumes.create.assert_not_called()

    def test_missing_profile_is_not_created(self):
        self.client.volumes.exists.return_value = False
        with self.assertRaisesRegex(RunnerError, "native_rollout_binding_invalid"):
            export_rollout(self.state, self.run_id)
        self.runtime.execute_job.assert_not_called()
        self.client.volumes.create.assert_not_called()

    def test_reconciles_retained_export_receipt_before_dispatch(self):
        receipts = self.run_dir / "rollout-receipts"
        receipts.mkdir()
        previous = receipts / "previous.json"
        previous.write_text("{}")
        export_rollout(self.state, self.run_id)
        self.runtime.recover_receipts.assert_called_once_with(
            self.client, [previous], kind="job"
        )

    def test_cleanup_uncertainty_blocks_new_reads_and_keeps_previous_output(self):
        from py_docker.errors import CleanupUnconfirmedError

        output = self.run_dir / "native-rollout.jsonl"
        output.write_bytes(b"previous verified export")
        self.runtime.recover_receipts.side_effect = CleanupUnconfirmedError(
            "recover owned export"
        )
        with self.assertRaisesRegex(RunnerError, "container_termination_unverified"):
            export_rollout(self.state, self.run_id)
        self.runtime.execute_job.assert_not_called()
        self.assertEqual(output.read_bytes(), b"previous verified export")

    def test_failed_read_does_not_publish_or_expose_stderr(self):
        self.runtime.execute_job.side_effect = None
        self.runtime.execute_job.return_value = self.results(
            exit_code=1, stdout=b"", stderr=b"private diagnostic"
        )
        with self.assertRaisesRegex(RunnerError, "^native_rollout_export_failed$"):
            export_rollout(self.state, self.run_id)
        self.assertFalse((self.run_dir / "native-rollout.jsonl").exists())

    def test_path_and_identity_and_content_refusals(self):
        cases = [
            ("native_rollout_not_unique", [b""], 1),
            ("native_rollout_path_invalid", [b"/home/runner/.codex/auth.json\n"], 1),
            (
                "native_rollout_path_invalid",
                [b"/home/runner/.codex/sessions/../auth.json\n"],
                1,
            ),
            ("native_rollout_size_invalid", [self.outputs[0], b"67108865"], 2),
            ("native_rollout_size_invalid", [self.outputs[0], b"2", b"{}\n"], 3),
            ("native_rollout_content_invalid", [self.outputs[0], b"2", b"xx"], 3),
            ("native_rollout_identity_mismatch", [self.outputs[0], b"2", b"{}"], 3),
        ]
        for code, outputs, reads in cases:
            with self.subTest(code=code, outputs=outputs[:2]):
                self.jobs.clear()
                self.outputs = outputs
                with self.assertRaisesRegex(RunnerError, code):
                    export_rollout(self.state, self.run_id)
                self.assertEqual(len(self.jobs), reads)
                self.assertFalse((self.run_dir / "native-rollout.jsonl").exists())


if __name__ == "__main__":
    unittest.main()
