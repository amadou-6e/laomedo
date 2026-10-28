"""Public proposal dictionary boundary for component and saved-flow callers."""

import laomedo.skills.operations.models as _operations_models


def proposal(value):
    return _operations_models.SkillProposal.from_payload(value).to_payload()
