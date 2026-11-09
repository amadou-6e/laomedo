"""Credentials target interfaces for provider migration (#277)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from laomedo.agents.agents.base.models.credentials import (
        CredentialAdmission,
        CredentialRequest,
    )


class BaseCredentialProvider(ABC):
    """Common credential admission; native refresh/probes remain provider-owned."""

    @abstractmethod
    def admit(self, request: CredentialRequest) -> CredentialAdmission:
        """Preserve native timing/identity; expose only explicit host launch material.

        No universal token borrowing or success-only release. Do not delete host
        login or claim unsupported validity/deadline constraints were enforced.
        """
