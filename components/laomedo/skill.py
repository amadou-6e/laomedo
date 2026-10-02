"""Pinned whole-skill reference for the existing runner registry."""

import re

from lfx.custom.custom_component.component import Component
from lfx.io import Output, StrInput
from lfx.schema import Data


class LaomedoSkill(Component):
    display_name = "Laomedo Skill"
    description = "Pass an immutable whole-skill revision to a Laomedo Codex Agent."
    icon = "BookOpen"
    name = "LaomedoSkill"
    inputs = [
        StrInput(name="skill_id", display_name="Skill ID", required=True),
        StrInput(name="revision_id", display_name="Skill Revision", required=True,
                 info="Exact sha256 revision in the runner's skill store."),
    ]
    outputs = [Output(name="skill", display_name="Skill Reference", method="skill_output")]

    def skill_output(self) -> Data:
        skill_id, revision = str(self.skill_id), str(self.revision_id)
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", skill_id):
            raise ValueError("invalid_skill_id")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", revision):
            raise ValueError("immutable_skill_revision_required")
        self.status = f"{skill_id} at {revision}"
        return Data(data={"skill_id": skill_id, "revision_id": revision, "tree_hash": revision})
