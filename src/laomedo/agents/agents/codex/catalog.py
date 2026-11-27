"""Provider-owned zero-turn model discovery and its native freshness policy."""

import asyncio
import time
from laomedo.agents.agents.codex.settings import MODEL_CATALOG_TTL_SECONDS
from laomedo.agents.agents.base.base import BaseModelCatalog
from laomedo.agents.agents.base.models import ModelCatalog


class CodexModelCatalog(BaseModelCatalog):
    """Own codex discovery cache; construction performs no native operation."""

    def __init__(self, agent):
        """Bind the provider's admitted discovery hooks and create private cache state."""
        self.agent = agent
        super().__init__()

    def list_models(self, *, refresh: bool = False) -> ModelCatalog:
        """Serialize and briefly cache metadata discovery; never submit a turn."""
        with self._lock:
            cached = self._cached
            if (
                not refresh
                and cached
                and time.monotonic() - cached[0] < MODEL_CATALOG_TTL_SECONDS
            ):
                return ModelCatalog.from_payload(cached[1])
            result = asyncio.run(self.agent._model_catalog())
            catalog = ModelCatalog.from_payload(result)
            self._cached = (time.monotonic(), result)
            return catalog
