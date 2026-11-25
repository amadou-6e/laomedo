"""GitHub and GitLab repository Skill component for Langflow."""

from urllib.parse import urlsplit

from laomedo.skills.interface.langflow.component import SkillComponent


class LaomedoGitHubSkill(SkillComponent):
    """Discover repository Skills and allow connected private GitHub reads."""

    display_name = "GitHub Skill"
    name = "LaomedoGitHubSkill"
    description = "Use Skills from GitHub and public GitLab repositories."

    def _validate_source(self, source: str) -> None:
        if not source:
            return
        parsed = urlsplit(source)
        if parsed.scheme != "https" or parsed.hostname not in {
            "github.com",
            "gitlab.com",
        }:
            raise ValueError("repository_skill_source_required")

    def skill_output(self):
        if not getattr(self, "source", ""):
            raise ValueError("repository_skill_source_required")
        return super().skill_output()
