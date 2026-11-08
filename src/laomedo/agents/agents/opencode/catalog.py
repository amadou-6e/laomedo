"""Provider-owned zero-turn model discovery and its native freshness policy."""

import asyncio
from laomedo.agents.agents.base.base import BaseAgentRuntime
import shutil
import time
from laomedo.agents.agents.opencode.settings import MODEL_CATALOG_TTL_SECONDS
from uuid import uuid4
from laomedo.agents.agents.base.base import BaseModelCatalog
from laomedo.agents.agents.base.models import ModelCatalogSnapshot
from laomedo.agents.agents.base.utils import failure_observation
from laomedo.agents.errors import RunnerError


class OpenCodeModelCatalog(BaseModelCatalog):
    """Own opencode discovery cache; construction performs no native operation."""

    def __init__(self, agent):
        """Bind the provider's admitted discovery hooks and create private cache state."""
        self.agent = agent
        super().__init__()

    def discover(self, *, refresh: bool = False) -> ModelCatalogSnapshot:
        """Discover connected native models without creating a session or turn."""
        if self.agent.transport_factory is None:
            raise RunnerError("opencode_isolated_transport_required")
        self.agent._recover_containers()
        with self._lock:
            cached = self._cached
            if (
                not refresh
                and cached
                and time.monotonic() - cached[0] < MODEL_CATALOG_TTL_SECONDS
            ):
                return ModelCatalogSnapshot.model_validate(cached[1])
            if not self.agent.lock.acquire(blocking=False):
                raise RunnerError("runner_busy")
            root = self.agent.state / "catalog" / str(uuid4())
            backend = None
            primary = None
            try:
                for name in ("workspace", "canonical", "store"):
                    (root / name).mkdir(parents=True)
                (root / "workspace/.agents/skills").mkdir(parents=True)
                backend = self.agent.transport_factory(root / "workspace", root)
                models = [
                    {"id": item["id"], "efforts": item["efforts"]}
                    for item in backend.models()
                ]
                for item in models:
                    self.agent._validate_provider(item["id"], "default")
                if not models:
                    raise RunnerError("opencode_model_not_connected")
                result = {"models": models, "submitted_turns": 0}
            except Exception as error:
                primary = failure_observation(error, stage="startup")
                raise
            finally:
                try:
                    if backend is not None:
                        try:
                            (
                                asyncio.run(backend.shutdown())
                                if isinstance(backend, BaseAgentRuntime)
                                else backend.close()
                            )
                        except RunnerError as cleanup:
                            raise RunnerError(
                                cleanup.code, observation=primary or cleanup.observation
                            ) from None
                finally:
                    try:
                        if root.exists() and not list(
                            root.joinpath("docker-receipts").glob("*.json")
                        ):
                            shutil.rmtree(root)
                    finally:
                        self.agent.lock.release()
            self._cached = (time.monotonic(), result)
            return ModelCatalogSnapshot.model_validate(result)
