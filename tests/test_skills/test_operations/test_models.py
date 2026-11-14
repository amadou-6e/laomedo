"""Skill operation payload and validation contracts."""

import json
import unittest
from pydantic import ValidationError

from laomedo.skills.operations.models.provenance import EditorProvenance
from laomedo.skills.operations.models.proposal import FileEdit
from laomedo.skills.operations.models.proposal import SkillProposal
from laomedo.skills.operations.utils.proposal import proposal
from laomedo.skills.registry.errors import SkillStoreError


class SkillProposalModelTests(unittest.TestCase):
    """Assert operation wire shapes and fail-closed model validation."""

    def test_multifile_proposal_roundtrips_the_existing_payload(self):
        payload = {
            "action": "modify",
            "message": "Update both files",
            "files": [
                {"path": "SKILL.md", "content": "# Skill\n"},
                {"path": "references/obsolete.md", "content": None},
            ],
        }
        model = SkillProposal.from_payload(payload)
        self.assertIsInstance(model.files[0], FileEdit)
        self.assertEqual(model.to_payload(), payload)
        self.assertEqual(proposal(json.dumps(payload)), payload)
        self.assertEqual(
            EditorProvenance.from_payload(
                {"kind": "agent", "run_id": "run-1"}
            ).to_payload(),
            {"kind": "agent", "run_id": "run-1"},
        )
        self.assertEqual(
            EditorProvenance.from_payload(None).to_payload(), {"kind": "operator"}
        )

    def test_invalid_proposals_keep_stable_codes_and_never_coerce(self):
        with self.assertRaisesRegex(SkillStoreError, "skill_operation_invalid"):
            SkillProposal.from_payload(
                {"action": "modify", "message": 123, "files": []}
            )
        with self.assertRaisesRegex(SkillStoreError, "skill_agent_provenance_required"):
            EditorProvenance.from_payload({"kind": "agent"})
        with self.assertRaises(ValidationError):
            FileEdit(path="../escape.md", content="bad")
        with self.assertRaises(ValidationError):
            FileEdit(path="safe.md", content=123)
