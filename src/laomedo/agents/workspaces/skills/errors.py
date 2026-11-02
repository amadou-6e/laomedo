"""Agent working-state preparation and skill-integrity refusals."""

from __future__ import annotations


class WorkspaceSkillError(ValueError):
    """Pinned skill materialization or workspace verification was refused.

    ``code`` identifies the failed reference, policy or integrity check;
    dispatch must not proceed with partially materialized skills."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
