"""Manual saves share the real registry/journal; publication has separate authority."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4
from support.paths import error_catalogue_path

from laomedo.skills.operations.manual import ManualSkillEditor
from laomedo.skills.interface.operations.server import SkillOperationServer
from support.http_server import RunningHTTPServer
from test_skills.test_operations.utils import make_operation_case


class ManualSkillEditorTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.case = make_operation_case(Path(temporary.name))
        self.editor = ManualSkillEditor(
            self.case.service, {"internal-test": {"edit": True, "publish": True}}
        )

    def save(self, **overrides):
        state = self.editor.editor("internal-test", self.case.initial["revision_id"])
        payload = dict(
            request_id=str(uuid4()),
            skill_id="internal-test",
            revision_id=state["head_revision"],
            commit_id=state["head_commit"],
            operation=copy.deepcopy(self.case.operation),
        )
        payload.update(overrides)
        return payload, self.editor.save(**payload)

    def publication(self, saved):
        return dict(
            skill_id="internal-test",
            revision_id=saved["skill"]["revision_id"],
            commit_id=saved["commit"]["commit_id"],
            expected_latest=self.case.initial["revision_id"],
        )

    def test_default_denied_and_editor_never_exposes_capabilities(self):
        denied = ManualSkillEditor(self.case.service)
        state = denied.editor("internal-test", self.case.initial["revision_id"])
        self.assertFalse(state["can_edit"])
        self.assertFalse(state["can_publish"])
        self.assertNotIn("ticket", json.dumps(state))
        with self.assertRaisesRegex(ValueError, "skill_manual_not_authorized"):
            denied.publish(
                skill_id="internal-test",
                revision_id=state["head_revision"],
                commit_id=state["head_commit"],
                expected_latest=state["latest_revision"],
            )

    def test_multifile_save_is_one_commit_and_durable_replay_does_not_reapply(self):
        payload, saved = self.save()
        self.assertEqual(saved["commit"]["files"], ["SKILL.md", "rules/one.md"])
        self.assertEqual(saved["commit"]["editor"], {"kind": "operator"})
        self.assertEqual(self.case.store.revision("internal-test"), self.case.initial)
        with self.case.service.connect() as db:
            db.execute("UPDATE requests SET expires=0")
        reloaded = ManualSkillEditor(
            self.case.service, {"internal-test": {"edit": True, "publish": True}}
        )
        self.assertEqual(reloaded.save(**payload), saved)
        self.assertEqual(
            len(
                self.case.service.history(
                    "internal-test", saved["skill"]["revision_id"]
                )["commits"]
            ),
            2,
        )
        changed = copy.deepcopy(payload)
        changed["operation"]["message"] = "different"
        with self.assertRaisesRegex(ValueError, "skill_manual_request_conflict"):
            reloaded.save(**changed)

    def test_stale_and_forbidden_batches_preserve_registry_and_history(self):
        payload, saved = self.save()
        stale = dict(payload, request_id=str(uuid4()))
        with self.assertRaisesRegex(ValueError, "skill_base_changed"):
            self.editor.save(**stale)
        bad = copy.deepcopy(self.case.operation)
        bad["files"].append({"path": "forbidden.md", "content": "denied"})
        with self.assertRaisesRegex(ValueError, "skill_edit_policy_denied"):
            self.save(operation=bad)
        history = self.case.service.history(
            "internal-test", saved["skill"]["revision_id"]
        )
        self.assertEqual(len(history["commits"]), 2)
        self.assertEqual(self.case.store.revision("internal-test"), self.case.initial)

    def test_separate_publish_grant_and_exact_multicommit_cumulative_promotion(self):
        _, first = self.save()
        second_operation = copy.deepcopy(self.case.operation)
        second_operation["files"][1]["content"] = "second edit\n"
        _, second = self.save(operation=second_operation)
        self.assertEqual(
            second["commit"]["parent_commit"], first["commit"]["commit_id"]
        )
        payload = self.publication(second)
        denied = ManualSkillEditor(self.case.service, {"internal-test": {"edit": True}})
        with self.assertRaisesRegex(ValueError, "skill_manual_not_authorized"):
            denied.publish(**payload)
        result = self.editor.publish(**payload)
        self.assertTrue(result["promotion_performed"])
        self.assertEqual(
            self.case.store.revision("internal-test")["revision_id"],
            second["skill"]["revision_id"],
        )
        self.assertEqual(self.editor.publish(**payload), result)
        self.assertEqual(
            len(
                self.case.service.history(
                    "internal-test", second["skill"]["revision_id"]
                )["commits"]
            ),
            3,
        )
        self.assertEqual(
            (self.case.root / "source/rules/one.md").read_bytes(), b"original\n"
        )

    def test_policy_revocation_and_changed_canonical_base_refuse_publication(self):
        _, saved = self.save()
        payload = self.publication(saved)
        original = self.case.service.policies.pop("internal-test")
        with self.assertRaisesRegex(ValueError, "skill_manual_not_authorized"):
            self.editor.publish(**payload)
        self.case.service.policies["internal-test"] = original
        # A real independent canonical promotion conflicts with the reviewed base.
        draft = self.case.store.create_draft(
            "internal-test", self.case.initial["revision_id"], original
        )
        (
            self.case.store.draft_workspace(draft["draft_id"]) / "rules/one.md"
        ).write_bytes(b"other publisher\n")
        frozen = self.case.store.freeze_draft(draft["draft_id"])
        self.case.store.promote_draft(
            draft["draft_id"],
            expected_base_revision=self.case.initial["revision_id"],
            reviewed_draft_hash=frozen["proposed_tree_hash"],
            expected_policy_hash=frozen["policy_ref"]["hash"],
        )
        with self.assertRaisesRegex(ValueError, "skill_manual_stale"):
            self.editor.publish(**payload)
        self.assertEqual(
            self.case.store.revision("internal-test")["revision_id"],
            frozen["proposed_tree_hash"],
        )

    def test_lost_save_and_publication_responses_reconcile_existing_effects(self):
        real_apply = self.case.service.apply

        def lose_response(*args, **kwargs):
            real_apply(*args, **kwargs)
            raise OSError("private path must not escape")

        state = self.editor.editor("internal-test", self.case.initial["revision_id"])
        payload = dict(
            request_id=str(uuid4()),
            skill_id="internal-test",
            revision_id=state["head_revision"],
            commit_id=state["head_commit"],
            operation=self.case.operation,
        )
        with patch.object(self.case.service, "apply", side_effect=lose_response):
            with self.assertRaises(OSError):
                self.editor.save(**payload)
        saved = self.editor.save(**payload)
        publication = self.publication(saved)
        real_promote = self.case.store.promote_draft

        def lose_publication(*args, **kwargs):
            real_promote(*args, **kwargs)
            raise OSError("response lost")

        with patch.object(
            self.case.store, "promote_draft", side_effect=lose_publication
        ):
            with self.assertRaises(OSError):
                self.editor.publish(**publication)
        result = self.editor.publish(**publication)
        self.assertEqual(self.editor.publish(**publication), result)
        with self.case.service.connect() as db:
            self.assertEqual(
                db.execute("SELECT COUNT(*) FROM manual_publications").fetchone()[0], 1
            )

    def test_manual_catalogue_covers_the_closed_public_failure_set(self):
        from laomedo.skills.operations.contract import MANUAL_ERROR_CODES

        catalog = json.loads(error_catalogue_path().read_text(encoding="utf-8"))
        for code in MANUAL_ERROR_CODES:
            self.assertTrue(
                all(
                    catalog[code][field].strip()
                    for field in ("title", "description", "recovery")
                )
            )

    def test_completed_effects_reconcile_after_write_revocation_without_new_authority(
        self,
    ):
        payload, saved = self.save()
        publication = self.publication(saved)
        real_promote = self.case.store.promote_draft

        def lose_response(*args, **kwargs):
            real_promote(*args, **kwargs)
            raise OSError("lost after durable promotion")

        with patch.object(self.case.store, "promote_draft", side_effect=lose_response):
            with self.assertRaises(OSError):
                self.editor.publish(**publication)
        self.editor.permissions.clear()
        self.case.service.policies.clear()
        self.assertEqual(self.editor.save(**payload), saved)
        result = self.editor.publish(**publication)
        self.assertEqual(result["revision_id"], saved["skill"]["revision_id"])
        self.assertEqual(self.editor.publish(**publication), result)
        with self.assertRaisesRegex(ValueError, "skill_manual_not_authorized"):
            self.editor.save(**dict(payload, request_id=str(uuid4())))
        self.assertEqual(
            self.case.store.revision("internal-test")["revision_id"],
            saved["skill"]["revision_id"],
        )

    def test_private_http_requires_auth_and_rejects_forged_editor_or_authority(self):
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError

        with RunningHTTPServer(
            SkillOperationServer(
                self.case.service,
                "x" * 32,
                0,
                manual_permissions={"internal-test": {"edit": True, "publish": True}},
            )
        ) as running:
            base = f"http://127.0.0.1:{running.server_port}/v1/skill-operations/"
            for authorized, body, expected in [
                (False, {}, 401),
                (
                    True,
                    {
                        "skill_id": "internal-test",
                        "revision_id": self.case.initial["revision_id"],
                        "editor": {"kind": "agent"},
                    },
                    400,
                ),
            ]:
                headers = {"Content-Type": "application/json"}
                if authorized:
                    headers["Authorization"] = "Bearer " + "x" * 32
                with self.assertRaises(HTTPError) as failure:
                    urlopen(
                        Request(
                            base + "editor",
                            data=json.dumps(body).encode(),
                            headers=headers,
                        )
                    )
                self.assertEqual(failure.exception.code, expected)
                self.assertNotIn(str(self.case.root), failure.exception.read().decode())

    def test_missing_copy_source_is_projected_as_manual_invalid(self):
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError

        state = self.editor.editor("internal-test", self.case.initial["revision_id"])
        body = {
            "request_id": str(uuid4()),
            "skill_id": "internal-test",
            "revision_id": state["head_revision"],
            "commit_id": state["head_commit"],
            "operation": {
                "action": "modify",
                "message": "Copy an absent source",
                "files": [{"path": "rules/two.md", "source_path": "absent.md"}],
            },
        }
        with RunningHTTPServer(
            SkillOperationServer(
                self.case.service,
                "x" * 32,
                0,
                manual_permissions={"internal-test": {"edit": True, "publish": True}},
            )
        ) as running:
            request = Request(
                f"http://127.0.0.1:{running.server_port}/v1/skill-operations/save",
                data=json.dumps(body).encode(),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + "x" * 32,
                },
            )
            with self.assertRaises(HTTPError) as failure:
                urlopen(request, timeout=5)
            with failure.exception as response:
                self.assertEqual(response.code, 400)
                self.assertEqual(
                    json.load(response), {"error_category": "skill_manual_invalid"}
                )
        self.assertEqual(self.case.store.revision("internal-test"), self.case.initial)
