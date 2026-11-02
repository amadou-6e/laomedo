"""Public proposal dictionary boundary for component and saved-flow callers."""

from laomedo.skills.operations.models import SkillProposal


def proposal(value):
    """Admit a complete edit proposal and translate validation failures to stable operation errors."""
    return SkillProposal.from_payload(value).to_payload()
