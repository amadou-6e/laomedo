"""Build explicit Skill boundary cases without starting services."""

from laomedo.skills.interface.operations.client import skill_request
from laomedo.skills.interface.operations.server import SkillOperationServer
from laomedo.skills.interface.sources.client import source_request
from laomedo.skills.interface.sources.server import SkillSourceServer
from test_skills.test_interface.models import SkillHTTPCase


def http_cases():
    """Return fresh records with independently fixed route/error expectations."""
    return (
        SkillHTTPCase(
            server_type=SkillSourceServer,
            client=source_request,
            route="/v1/skill-sources/discover",
            method="discover",
            body={"source": "source"},
            prefix="LAOMEDO_SKILL_SOURCE",
            fallback="source_unavailable",
            client_error="source_discovery_failed",
        ),
        SkillHTTPCase(
            server_type=SkillOperationServer,
            client=skill_request,
            route="/v1/skill-operations/history",
            method="history",
            body={"skill_id": "skill", "revision_id": "revision", "before": ""},
            prefix="LAOMEDO_SKILL_OPERATION",
            fallback="skill_operation_refused",
            client_error="skill_operation_unavailable",
        ),
    )
