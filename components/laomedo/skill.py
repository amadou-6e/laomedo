"""Local folder Skill component for Langflow."""

from copy import deepcopy
from urllib.parse import urlsplit

from laomedo.skills.interface.langflow.component import SkillComponent


class LaomedoLocalSkill(SkillComponent):
    """Discover local Skill folders and execute an admitted immutable reference."""

    display_name = "Local Skill"
    name = "LaomedoLocalSkill"
    description = "Use and edit Skills from local folders."
    select_current_revision = True
    inputs = [
        deepcopy(item)
        for item in SkillComponent.inputs
        if item.name not in {"github_connection", "private_repository_id"}
    ]
    for item in inputs:
        if item.name in {"revision_id", "commit_id"}:
            item.show = False
            item.required = False

    def _validate_source(self, source: str) -> None:
        if urlsplit(source).scheme.lower() in {"http", "https", "ssh", "git"}:
            raise ValueError("local_skill_source_required")
