import copy
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from urllib import request
from urllib import error

from laomedo.skills.registry.store import SkillStore
from laomedo.skills.registry.errors import SkillStoreError
from laomedo.skills.registry.errors import ConflictError
from laomedo.skills.operations.service import SkillOperations
from laomedo.skills.operations.utils.proposal import proposal
from test_skills.test_operations.utils import make_operation_case
from support.http_server import RunningHTTPServer
from laomedo.skills.interface.operations.server import SkillOperationServer as server


class SkillOperationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.case = make_operation_case(Path(temporary.name))

    def test_prepare_does_not_embed_viewer_image_data_in_agent_snapshot(self):
        source = self.case.root / "source"
        (source / "image.png").write_bytes(b"\x89PNG\r\n\x1a\ninternal-control")
        record = self.case.store.import_skill("image-test", source)
        service = SkillOperations(
            self.case.store,
            self.case.root / "image-history.db",
            {"image-test": self.case.policy},
        )
        snapshot = service.prepare("image-test", record["revision_id"])["snapshot"]
        image = next(file for file in snapshot["files"] if file["path"] == "image.png")
        self.assertEqual(image["kind"], "binary")
        self.assertIsNone(image["text"])
        self.assertNotIn("image_data_url", json.dumps(snapshot))

    def test_atomic_multifile_revision_and_replay(self):
        reservation = self.case.prepare()
        result = self.case.service.apply(reservation["ticket"], self.case.operation)
        self.assertEqual(result["commit"]["files"], ["SKILL.md", "rules/one.md"])
        self.assertEqual(result["commit"]["parent_commit"], reservation["base_commit"])
        self.assertEqual(self.case.store.revision("internal-test"), self.case.initial)
        self.assertEqual(
            self.case.service.apply(reservation["ticket"], self.case.operation), result
        )
        self.assertFalse(result["promotion_performed"])
        self.assertIn("updated", result["commit"]["patch"])
        history = self.case.service.history(
            "internal-test", result["skill"]["revision_id"]
        )
        self.assertEqual(len(history["commits"]), 2)
        self.assertEqual(
            history["commits"][0]["commit_id"], result["commit"]["commit_id"]
        )

    def test_conflicting_concurrent_edits_do_not_partially_apply(self):
        first, second = self.case.prepare(), self.case.prepare()
        self.case.service.apply(first["ticket"], self.case.operation)
        with self.assertRaisesRegex(ConflictError, "skill_base_changed"):
            self.case.service.apply(second["ticket"], self.case.operation)
        self.assertEqual(
            len(
                self.case.service.history(
                    "internal-test", self.case.initial["revision_id"]
                )["commits"]
            ),
            2,
        )

    def test_policy_denies_entire_batch(self):
        reservation = self.case.prepare()
        operation = copy.deepcopy(self.case.operation)
        operation["files"].append({"path": "secret.md", "content": "no"})
        with self.assertRaisesRegex(SkillStoreError, "skill_edit_policy_denied"):
            self.case.service.apply(reservation["ticket"], operation)
        self.assertEqual(self.case.store.revision("internal-test"), self.case.initial)
        self.assertEqual(
            len(
                self.case.service.history(
                    "internal-test", self.case.initial["revision_id"]
                )["commits"]
            ),
            1,
        )

    def test_revert_has_distinct_commit_but_same_tree(self):
        first = self.case.service.apply(
            self.case.prepare()["ticket"], self.case.operation
        )
        reservation = self.case.prepare(
            first["skill"]["revision_id"], first["commit"]["commit_id"]
        )
        reverted = self.case.service.apply(
            reservation["ticket"],
            {
                "action": "modify",
                "message": "Revert",
                "files": [
                    {"path": "SKILL.md", "content": self.case.original},
                    {"path": "rules/one.md", "content": "original\n"},
                ],
            },
        )
        self.assertEqual(
            reverted["skill"]["revision_id"], self.case.initial["revision_id"]
        )
        self.assertNotEqual(reverted["commit"]["commit_id"], reservation["base_commit"])
        self.assertEqual(
            len(
                self.case.service.history(
                    "internal-test", self.case.initial["revision_id"]
                )["commits"]
            ),
            3,
        )
        with self.assertRaises(ConflictError):
            self.case.prepare()

    def test_path_aliases_and_model_authority_rejected(self):
        for path in ("../escape.md", "rules/../escape.md", "rules\\one.md"):
            with self.assertRaises(ValueError):
                proposal(
                    {**self.case.operation, "files": [{"path": path, "content": "no"}]}
                )
        with self.assertRaises(ValueError):
            proposal({**self.case.operation, "run_id": "model-forged"})
        with self.assertRaises(ValueError):
            proposal(
                {
                    **self.case.operation,
                    "files": [
                        {"path": "a.md", "content": ""},
                        {"path": "A.md", "content": ""},
                    ],
                }
            )

    def test_replay_conflict_expiry_and_revocation(self):
        reservation = self.case.prepare()
        self.case.service.apply(reservation["ticket"], self.case.operation)
        with self.assertRaises(ConflictError):
            self.case.service.apply(
                reservation["ticket"], {**self.case.operation, "message": "different"}
            )
        self.case.service.policies.clear()
        with self.assertRaisesRegex(ValueError, "skill_edit_not_authorized"):
            self.case.service.apply(reservation["ticket"], self.case.operation)
        self.case.service.policies["internal-test"] = self.case.policy
        with self.case.service.connect() as db:
            db.execute("UPDATE requests SET expires=0")
        with self.assertRaisesRegex(ValueError, "skill_ticket_expired"):
            self.case.service.apply(reservation["ticket"], self.case.operation)

    def test_add_delete_and_history_integrity(self):
        operation = {
            "action": "modify",
            "message": "Replace a rule",
            "files": [
                {"path": "rules/one.md", "content": None},
                {"path": "rules/two.md", "content": "new\n"},
            ],
        }
        result = self.case.service.apply(
            self.case.prepare()["ticket"],
            operation,
            editor={"kind": "agent", "run_id": "trusted-adapter-run"},
        )
        self.assertEqual(result["commit"]["editor"]["run_id"], "trusted-adapter-run")
        with self.case.service.connect() as db:
            db.execute(
                "UPDATE commits SET record='{}' WHERE id=?",
                (result["commit"]["commit_id"],),
            )
        with self.assertRaisesRegex(ValueError, "skill_history_integrity_failure"):
            self.case.service.history("internal-test", result["skill"]["revision_id"])

    def test_http_auth_and_exact_shape(self):
        resources = ExitStack()
        self.addCleanup(resources.close)
        service = resources.enter_context(
            RunningHTTPServer(server(self.case.service, "x" * 32, port=0))
        )
        url = (
            "http://127.0.0.1:"
            + str(service.server_port)
            + "/v1/skill-operations/prepare"
        )
        payload = {
            "skill_id": "internal-test",
            "revision_id": self.case.initial["revision_id"],
            "commit_id": "",
        }

        def call(token, body):
            return request.urlopen(
                request.Request(
                    url,
                    data=json.dumps(body).encode(),
                    headers={
                        "Authorization": "Bearer " + token,
                        "Content-Type": "application/json",
                    },
                ),
                timeout=5,
            )

        with self.assertRaises(error.HTTPError) as failure:
            call("wrong", payload)
        self.assertEqual(failure.exception.code, 401)
        with call("x" * 32, payload) as response:
            self.assertIn("ticket", json.load(response))
        with self.assertRaises(error.HTTPError):
            call("x" * 32, {**payload, "policy": self.case.policy})

    def test_comparison_is_cumulative_from_selected_snapshot_to_pinned_current(self):
        prepared = self.case.prepare()
        first = self.case.service.apply(prepared["ticket"], self.case.operation)
        prepared2 = self.case.prepare(
            first["skill"]["revision_id"], first["commit"]["commit_id"]
        )
        second = self.case.service.apply(
            prepared2["ticket"],
            {
                "action": "modify",
                "message": "Add another rule",
                "files": [{"path": "rules/two.md", "content": "another rule\n"}],
            },
        )
        compared = self.case.service.compare(
            "internal-test", prepared["base_commit"], second["skill"]["revision_id"]
        )
        self.assertEqual(compared["base_revision"], self.case.initial["revision_id"])
        self.assertEqual(compared["current_revision"], second["skill"]["revision_id"])
        self.assertEqual(
            [file["path"] for file in compared["files"]],
            ["SKILL.md", "rules/one.md", "rules/two.md"],
        )
        self.assertIn("+another rule\n", compared["patch"])
        self.assertIn("+updated\n", compared["patch"])
        self.assertNotIn("another rule\\n", compared["patch"])
        pinned = self.case.service.compare(
            "internal-test", prepared["base_commit"], first["skill"]["revision_id"]
        )
        self.assertEqual(len(pinned["files"]), 2)
        same = self.case.service.compare(
            "internal-test", first["commit"]["commit_id"], first["skill"]["revision_id"]
        )
        self.assertEqual(same["files"], [])
        self.assertEqual(same["patch"], "")

    def test_comparison_additions_deletions_and_missing_final_newline(self):
        prepared = self.case.prepare()
        result = self.case.service.apply(
            prepared["ticket"],
            {
                "action": "modify",
                "message": "Replace rule",
                "files": [
                    {"path": "rules/one.md", "content": None},
                    {"path": "rules/two.md", "content": "no final newline"},
                ],
            },
        )
        compared = self.case.service.compare(
            "internal-test", prepared["base_commit"], result["skill"]["revision_id"]
        )
        self.assertEqual(
            [item["status"] for item in compared["files"]], ["deleted", "added"]
        )
        self.assertIn("\\ No newline at end of file", compared["patch"])
        self.assertIn("--- /dev/null", compared["patch"])
        self.assertIn("+++ /dev/null", compared["patch"])

    def test_comparison_refuses_cross_skill_commit_and_corrupt_current(self):
        prepared = self.case.prepare()
        with self.assertRaises(SkillStoreError):
            self.case.service.compare(
                "other-skill", prepared["base_commit"], self.case.initial["revision_id"]
            )
        folder = (
            self.case.store._revision_dir(
                "internal-test", self.case.initial["revision_id"]
            )
            / "bundle"
        )
        (folder / "SKILL.md").write_bytes(b"corrupt")
        with self.assertRaises(ValueError):
            self.case.service.compare(
                "internal-test",
                prepared["base_commit"],
                self.case.initial["revision_id"],
            )

    def test_comparison_binary_metadata_does_not_export_bytes(self):
        source = self.case.root / "binary-source"
        source.mkdir()
        (source / "SKILL.md").write_bytes(self.case.original.encode())
        (source / "asset.pdf").write_bytes(b"\0private-before")
        base = self.case.store.import_skill("binary-skill", source)
        service = SkillOperations(
            self.case.store,
            self.case.root / "binary.db",
            {"binary-skill": self.case.policy},
        )
        root_commit = service.prepare("binary-skill", base["revision_id"])[
            "base_commit"
        ]
        (source / "asset.pdf").write_bytes(b"\0private-after")
        current = self.case.store._store_revision(
            "binary-skill", source, base["revision_id"]
        )
        result = service.compare("binary-skill", root_commit, current["revision_id"])
        self.assertTrue(result["files"][0]["binary"])
        self.assertIn("Binary files differ", result["patch"])
        self.assertNotIn("private-before", json.dumps(result))
        self.assertNotIn("private-after", json.dumps(result))

    def test_comparison_unicode_separators_do_not_create_false_missing_newlines(self):
        prepared = self.case.prepare()
        result = self.case.service.apply(
            prepared["ticket"],
            {
                "action": "modify",
                "message": "Keep Unicode line content",
                "files": [
                    {"path": "rules/one.md", "content": "first\fmiddle\u2028last\n"}
                ],
            },
        )
        comparison = self.case.service.compare(
            "internal-test", prepared["base_commit"], result["skill"]["revision_id"]
        )
        self.assertIn("+first\fmiddle\u2028last\n", comparison["patch"])
        self.assertNotIn("\\ No newline at end of file", comparison["patch"])
