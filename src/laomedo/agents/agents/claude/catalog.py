"""Provider-owned zero-turn model discovery and its native freshness policy."""

from concurrent.futures import Future, TimeoutError as FutureTimeout
from copy import deepcopy
import time
from laomedo.agents.agents.claude.settings import MODEL_CATALOG_TTL_SECONDS
from laomedo.agents.agents.base.base import BaseModelCatalog
from laomedo.agents.agents.base.models import ModelCatalogSnapshot
from laomedo.agents.errors import RunnerError


class ClaudeModelCatalog(BaseModelCatalog):
    """Own claude discovery cache; construction performs no native operation."""

    def __init__(self, agent):
        """Bind the provider's admitted discovery hooks and create private cache state."""
        self.agent = agent
        super().__init__()

    def discover(self, *, refresh: bool = False) -> ModelCatalogSnapshot:
        """Share an in-flight discovery across simultaneous editor refreshes."""
        with self._lock:
            cached = self._cached
            if (
                not refresh
                and cached
                and time.monotonic() - cached[0] < MODEL_CATALOG_TTL_SECONDS
            ):
                return ModelCatalogSnapshot.model_validate(deepcopy(cached[1]))
            pending = self._pending
            owner = pending is None
            if owner:
                pending = self._pending = Future()
        if not owner:
            try:
                return ModelCatalogSnapshot.model_validate(
                    deepcopy(pending.result(timeout=65))
                )
            except FutureTimeout:
                raise RunnerError(
                    "runner_model_catalog_unavailable_check_runner_connection"
                ) from None
        try:
            result = self.agent._discover_models()
            with self._lock:
                self._cached = (time.monotonic(), deepcopy(result))
            pending.set_result(result)
            return ModelCatalogSnapshot.model_validate(deepcopy(result))
        except Exception as exc:
            pending.set_exception(exc)
            raise
        finally:
            with self._lock:
                self._pending = None
