"""Public proposal dictionary boundary for component and saved-flow callers."""

from laomedo.skills.operations.models import SkillProposal


def proposal(value):
    return SkillProposal.from_payload(value).to_payload()
