"""No-model host dispatch identity controls for the prospective live graph."""
import unittest
from importlib.util import find_spec
from laomedo.agents.providers.codex.native.models import CodexLaunch
import tempfile
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.append(str(Path(__file__).resolve().parents[1]))
from experiments.exp139.models import GitMetadataLaunch, MailboxLaunch
from experiments.exp139.bindings import BoundRunner; from experiments.exp139.bindings import GitMetadataAppServer; from experiments.exp139.bindings import MailboxAppServer; from experiments.exp139.settings import GIT_OVERRIDE; from experiments.exp139.settings import PROFILE_OVERRIDES; from experiments.exp139.bindings import request_digest
from laomedo.agents.providers.codex.runner import CodexRunner as LocalRunner; from laomedo.agents.runtime.errors import RunnerError; from laomedo.agents.providers.codex.native.server import AppServer


class BindingTests(unittest.TestCase):
    @unittest.skipUnless(find_spec("py_docker"), "Requires the optional Docker runtime")
    def test_mailbox_only_replaces_trusted_mediator_mount_and_bootstrap(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            launch=CodexLaunch(workspace=root,canonical=root,store_mount=root,image="sha256:"+"a"*64,
                capability=root.joinpath("capability"),mediator_url="http://127.0.0.1",mediator_instance="internal",
                run_id="run",launch_token="private-owner")
            with patch.object(GitMetadataAppServer,"__init__",return_value=None) as parent:
                MailboxAppServer(launch,root)
            prepared=parent.call_args.args[0]
            self.assertIsInstance(prepared,MailboxLaunch)
            spec=prepared.to_container_spec()
            self.assertEqual(spec.command[-2:],["app-server","--stdio"])
            self.assertIn("node /run/laomedo/relay.mjs",spec.command[2])
            self.assertEqual(spec.environment["GIT_EXEC_PATH"].get_secret_value(),"/run/laomedo/bin")
            self.assertEqual(spec.image,launch.image)
            self.assertEqual(prepared.launch_token,launch.launch_token)
            mounts={mount.target:mount for mount in spec.mounts}
            self.assertTrue(mounts["/run/laomedo/mediate.mjs"].source.endswith("mailbox_client.mjs"))
            self.assertTrue(mounts["/run/laomedo/mediate.mjs"].read_only)
            self.assertTrue(mounts["/run/laomedo/relay.mjs"].read_only)
            self.assertNotIn("auth.json",prepared.model_dump_json())

    @unittest.skipUnless(find_spec("py_docker"), "Requires the optional Docker runtime")
    def test_mailbox_does_not_start_for_no_mediator_request(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            launch=CodexLaunch(workspace=root,canonical=root,store_mount=root,image="sha256:"+"a"*64)
            with patch.object(GitMetadataAppServer,"__init__",return_value=None) as parent:
                MailboxAppServer(launch,root)
            spec=parent.call_args.args[0].to_container_spec()
            self.assertEqual(spec.command,GitMetadataLaunch.from_launch(launch).to_container_spec().command)
            self.assertFalse(any(mount.target=="/run/laomedo/relay.mjs" for mount in spec.mounts))
            self.assertNotIn("LAOMEDO_MEDIATION_FILE_STDIO",spec.environment)

    def make_runner(self, request, case="success"):
        calls = []
        with patch.object(LocalRunner, "__init__", return_value=None):
            runner = BoundRunner(approved_requests={request_digest(request): case},
                authorization_factory=lambda: calls.append("issued") or "fixture-reference")
        return runner, calls

    def test_host_selects_grant_but_preserves_graph_request_hash(self):
        original = {"task": "frozen task", "model": "fixture"}
        runner, calls = self.make_runner(original)
        expected = request_digest(original)
        with patch.object(LocalRunner, "_prepare", return_value={}) as prepare:
            runner._prepare(original, request_hash=expected)
            self.assertEqual(prepare.call_args.kwargs["request_hash"], expected)
            self.assertEqual(prepare.call_args.args[0]["github_authorization_ref"], "fixture-reference")
        self.assertNotIn("github_authorization_ref", original)
        self.assertEqual(calls, ["issued"])

    def test_modified_or_graph_supplied_scope_and_duplicate_refuse(self):
        original = {"task": "frozen task"}
        runner, calls = self.make_runner(original)
        for request in ({"task": "changed"}, {**original, "github_authorization_ref": "injected"}):
            with self.assertRaisesRegex(RunnerError, "experiment_request_binding_denied"):
                runner._prepare(request)
        with patch.object(LocalRunner, "_prepare", side_effect=RunnerError("setup_failed")):
            with self.assertRaises(RunnerError):
                runner._prepare(original)
        with self.assertRaisesRegex(RunnerError, "experiment_request_binding_denied"):
            runner._prepare(original)
        self.assertEqual(calls, ["issued"])

    def test_failure_case_has_no_git_authorization(self):
        original = {"task": "failure fixture"}
        runner, calls = self.make_runner(original, "failure")
        with patch.object(LocalRunner, "_prepare", return_value={}) as prepare:
            runner._prepare(original)
            self.assertNotIn("github_authorization_ref", prepare.call_args.args[0])
        self.assertEqual(calls, [])

    def test_supervisor_selected_only_from_host_case_and_scope(self):
        for case in ("success", "failure", "rejection"):
            runner, _ = self.make_runner({"task": case}, case)
            runner.lease_service = Path("mediated")
            runner.nonpublishing_lease_service = Path("ordinary")
            runner.execution_cases["run"] = case
            def execute(*args, **kwargs):
                return runner.lease_service
            with patch.object(LocalRunner, "status", return_value={"github_scope": {} } if case == "success" else {}), \
                    patch.object(LocalRunner, "_execute", side_effect=execute):
                self.assertEqual(runner._execute("run", "task", resume=False),
                                 Path("mediated" if case == "success" else "ordinary"))
            self.assertEqual(runner.lease_service, Path("mediated"))
            with patch.object(LocalRunner, "status", return_value={} if case == "success" else {"github_scope": {}}), \
                    patch.object(LocalRunner, "_execute") as execute:
                with self.assertRaisesRegex(RunnerError, "experiment_supervisor_scope_mismatch"):
                    runner._execute("run", "task", resume=False)
                execute.assert_not_called()
        with self.assertRaisesRegex(RunnerError, "experiment_resume_denied"):
            runner.resume("run", "task", "hash")

    def test_consumed_binding_survives_restart_and_failed_preparation(self):
        request = {"task": "new"}
        old = request_digest({"task": "old"})
        with tempfile.TemporaryDirectory() as directory:
            def make():
                with patch.object(LocalRunner, "__init__", return_value=None):
                    return BoundRunner(approved_requests={request_digest(request): "failure", old: "success"},
                        authorization_factory=lambda: self.fail("old scope issued"),
                        binding_state=Path(directory)/"bindings.sqlite", seed_consumed=[old])
            first = make()
            with patch.object(LocalRunner, "_prepare", side_effect=RunnerError("setup_failed")):
                with self.assertRaisesRegex(RunnerError, "setup_failed"):
                    first._prepare(request)
            second = make()
            for payload in (request, {"task": "old"}):
                with self.assertRaisesRegex(RunnerError, "experiment_request_binding_denied"):
                    second._prepare(payload)

    def test_permission_override_preserves_capability_redaction(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            capability=root.joinpath("capability")
            capability.write_text("dummy-private-value")
            launch=CodexLaunch(workspace=root,canonical=root,store_mount=root,image="sha256:"+"a"*64,
                capability=capability,mediator_url="http://127.0.0.1",mediator_instance="internal",
                run_id="run",launch_token="private-owner")
            with patch.object(AppServer,"__init__",return_value=None) as parent:
                GitMetadataAppServer(launch,root)
                self.assertIsInstance(parent.call_args.args[0],GitMetadataLaunch)
                self.assertEqual(parent.call_args.kwargs["secret_redactions"],("dummy-private-value",))
                MailboxAppServer(launch,root,lifetime_seconds=321,env={"DOCKER_HOST":"unix:///selected.sock"})
                prepared=parent.call_args.args[0]
                self.assertIsInstance(prepared,MailboxLaunch)
                self.assertEqual(prepared.launch_token,launch.launch_token)
                self.assertEqual(parent.call_args.kwargs["lifetime_seconds"],321)
                self.assertEqual(parent.call_args.kwargs["env"],{"DOCKER_HOST":"unix:///selected.sock"})

    def test_effective_override_keeps_original_policy_plus_only_git_rule(self):
        # Parse the literal table, not the CLI's dotted-key parser.
        import re
        rules = re.findall(r'"([^"]+)"="(read|write|deny)"', GIT_OVERRIDE)
        self.assertEqual(dict(rules), {':root':'read', ':workspace_roots':'write',
                '/home/runner/.codex/auth.json':'deny', '/draft/.git':'write'})
        self.assertEqual(len(rules),4)
        self.assertIn('network={enabled=false}', GIT_OVERRIDE)
        self.assertIn('default_permissions="container-edit"', PROFILE_OVERRIDES)
        self.assertIn('approval_policy="never"', PROFILE_OVERRIDES)
