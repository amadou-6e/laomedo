"""Binary byte admission, immutable copies and all-or-nothing edit history."""

import base64
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from laomedo.skills.operations.models import FileEdit, SkillProposal
from laomedo.skills.registry.errors import SkillStoreError
from test_skills.test_operations.utils import make_operation_case


class BinaryEditTests(unittest.TestCase):
    def test_old_text_request_keeps_its_exact_canonical_hash_and_projection(self):
        payload = {
            "action": "modify",
            "message": "Update",
            "files": [
                {"path": "rules/a.md", "content": "hello"},
                {"path": "rules/b.md", "content": None},
            ],
        }
        expected = b'{"action":"modify","files":[{"content":"hello","path":"rules/a.md"},{"content":null,"path":"rules/b.md"}],"message":"Update"}'
        result = SkillProposal.from_payload(payload).to_payload()
        self.assertEqual(result, payload)
        self.assertEqual(
            hashlib.sha256(
                json.dumps(result, sort_keys=True, separators=(",", ":")).encode()
            ).digest(),
            hashlib.sha256(expected).digest(),
        )

    def test_binary_forms_preserve_raw_bytes_and_reject_noncanonical_or_mixed_inputs(
        self,
    ):
        data = b"\x89PNG\r\n\x1a\n\x00\xff"
        edit = {
            "path": "image.png",
            "content": base64.b64encode(data).decode(),
            "encoding": "base64",
        }
        self.assertEqual(FileEdit.from_payload(edit).to_bytes({}), data)
        self.assertEqual(FileEdit.from_payload(edit).to_payload(), edit)
        copy = FileEdit.from_payload({"path": "copy.png", "source_path": "image.png"})
        self.assertEqual(copy.to_bytes({"image.png": data}), data)
        for value in [
            {**edit, "content": "AB=="},
            {**edit, "content": "YQ==\n"},
            {**edit, "content": None},
            {**edit, "encoding": "url"},
            {**edit, "source_path": "other.png"},
            {"path": "copy.png", "source_path": "../escape"},
            {"path": "copy.png"},
            {**edit, "content": base64.b64encode(b"x" * (512 * 1024 + 1)).decode()},
        ]:
            with self.subTest(value=set(value)), self.assertRaises(SkillStoreError):
                FileEdit.from_payload(value)

    def test_upload_then_delete_and_base_copy_is_atomic_and_traceable(self):
        with tempfile.TemporaryDirectory() as temporary:
            case = make_operation_case(Path(temporary))
            case.policy.update(
                allow_assets=True,
                allowed_suffixes=[".md", ".png"],
                allowed_paths=[
                    "SKILL.md",
                    "rules/one.md",
                    "image.png",
                    "rules/image.png",
                ],
            )
            case.service.policies["internal-test"] = case.policy
            data = b"\x89PNG\r\n\x1a\n\x00\xff"
            first = case.service.apply(
                case.prepare()["ticket"],
                {
                    "action": "modify",
                    "message": "Upload image",
                    "files": [
                        {
                            "path": "image.png",
                            "content": base64.b64encode(data).decode(),
                            "encoding": "base64",
                        }
                    ],
                },
            )
            base = first["skill"]["revision_id"]
            reservation = case.prepare(base, first["commit"]["commit_id"])
            second = case.service.apply(
                reservation["ticket"],
                {
                    "action": "modify",
                    "message": "Move image",
                    "files": [
                        {"path": "image.png", "content": None},
                        {"path": "rules/image.png", "source_path": "image.png"},
                    ],
                },
            )
            bundle = (
                case.store._revision_dir(
                    "internal-test", second["skill"]["revision_id"]
                )
                / "bundle"
            )
            self.assertEqual((bundle / "rules/image.png").read_bytes(), data)
            self.assertFalse((bundle / "image.png").exists())
            self.assertEqual(
                (
                    case.store._revision_dir("internal-test", base) / "bundle/image.png"
                ).read_bytes(),
                data,
            )
            self.assertEqual(
                second["commit"]["files"], ["image.png", "rules/image.png"]
            )
            self.assertEqual(
                len(
                    case.service.history(
                        "internal-test", second["skill"]["revision_id"]
                    )["commits"]
                ),
                3,
            )

    def test_binary_text_path_and_same_batch_source_refuse_without_partial_history(
        self,
    ):
        with tempfile.TemporaryDirectory() as temporary:
            case = make_operation_case(Path(temporary))
            before = case.service.history("internal-test", case.initial["revision_id"])
            for edits, code in [
                (
                    [{"path": "rules/two.md", "content": "AP8=", "encoding": "base64"}],
                    "skill_edit_policy_denied",
                ),
                (
                    [
                        {"path": "rules/two.md", "content": "new"},
                        {"path": "rules/one.md", "source_path": "rules/two.md"},
                    ],
                    "skill_file_missing",
                ),
            ]:
                with (
                    self.subTest(code=code),
                    self.assertRaisesRegex(SkillStoreError, code),
                ):
                    case.service.apply(
                        case.prepare()["ticket"],
                        {
                            "action": "modify",
                            "message": "Refused batch",
                            "files": edits,
                        },
                    )
                self.assertEqual(
                    case.service.history("internal-test", case.initial["revision_id"]),
                    before,
                )
                self.assertEqual(case.store.revision("internal-test"), case.initial)
