"""Exercise one cache-observation contract against each actual provider catalogue."""

from concurrent.futures import Future
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import threading
import unittest
from unittest.mock import AsyncMock, Mock

from pydantic import ValidationError

from laomedo.agents.agents.base.base import BaseModelCatalog
from laomedo.agents.agents.codex.catalog import CodexModelCatalog
from laomedo.agents.agents.claude.catalog import ClaudeModelCatalog
from laomedo.agents.agents.opencode.catalog import OpenCodeModelCatalog
from laomedo.agents.agents.base.models import ModelCatalog
from laomedo.agents.agents.base.models import ModelOption


class CatalogContractTests(unittest.TestCase):
    """Native freshness differs; observation and waiting guarantees do not."""

    def catalogs(self):
        """Compose real cache owners with forbidden native-discovery callbacks."""
        agent = SimpleNamespace(
            _model_catalog=Mock(side_effect=AssertionError("native discovery")),
            _discover_models=Mock(side_effect=AssertionError("native discovery")),
        )
        return [
            kind(agent)
            for kind in (CodexModelCatalog, ClaudeModelCatalog, OpenCodeModelCatalog)
        ]

    def discovery_catalogs(self, root):
        """Use real catalog/cache owners with explicit native protocol doubles."""
        for kind in (CodexModelCatalog, ClaudeModelCatalog, OpenCodeModelCatalog):
            payload = {
                "models": [
                    {
                        "id": "provider/model",
                        "name": "Reported model",
                        "efforts": ["low"],
                    }
                ],
                "submitted_turns": 0,
            }
            backend = Mock()
            backend.models.return_value = [
                {
                    "id": "provider/model",
                    "efforts": ["low"],
                    "metadata": {
                        "name": "Reported model",
                        "api_key": "excluded-synthetic-value",
                    },
                }
            ]
            agent = SimpleNamespace(
                state=Path(root) / kind.__name__,
                lock=threading.Lock(),
                _model_catalog=AsyncMock(return_value=payload),
                _discover_models=Mock(return_value=payload),
                _recover_containers=Mock(),
                _validate_provider=Mock(),
                transport_factory=Mock(return_value=backend),
            )
            yield kind(agent), agent, backend

    def test_one_typed_consumer_reads_each_provider_without_discovery_turns(self):
        """All catalog classes expose the same labels/options without raw metadata."""
        with TemporaryDirectory() as root:
            for catalog, agent, backend in self.discovery_catalogs(root):
                with self.subTest(catalog=type(catalog).__name__):
                    result = catalog.list_models()
                    self.assertIsInstance(result, ModelCatalog)
                    model = result.models[0]
                    self.assertIsInstance(model, ModelOption)
                    self.assertEqual(model.id, "provider/model")
                    self.assertEqual(model.display_name, "Reported model")
                    self.assertEqual(model.reasoning_efforts, ["low"])
                    self.assertIsNone(model.default_reasoning_effort)
                    self.assertIsNone(result.default_model_id)
                    self.assertEqual(result.submitted_turns, 0)
                    self.assertNotIn(
                        "excluded-synthetic-value", result.model_dump_json()
                    )
                    model.reasoning_efforts.append("caller mutation")
                    self.assertEqual(
                        catalog.list_models().models[0].reasoning_efforts, ["low"]
                    )

    def test_invalid_refresh_preserves_each_previous_successful_cache(self):
        """Invalid provider data cannot poison a successful discovery observation."""
        with TemporaryDirectory() as root:
            for catalog, agent, backend in self.discovery_catalogs(root):
                with self.subTest(catalog=type(catalog).__name__):
                    original = catalog.list_models()
                    invalid = {
                        "models": [{"id": "provider/model", "efforts": "not-a-list"}]
                    }
                    agent._model_catalog.return_value = invalid
                    agent._discover_models.return_value = invalid
                    backend.models.return_value = invalid["models"]
                    with self.assertRaises(ValidationError):
                        catalog.list_models(refresh=True)
                    self.assertEqual(catalog.snapshot(), original)
                    self.assertEqual(catalog.list_models(), original)

    def test_reported_defaults_are_validated_without_implicit_selection(self):
        """Known defaults remain explicit; absence is never the first listed choice."""
        catalog = ModelCatalog(
            models=[
                ModelOption(
                    id="reported",
                    reasoning_efforts=["low", "high"],
                    default_reasoning_effort="low",
                )
            ],
            default_model_id="reported",
        )
        self.assertEqual(catalog.default_model_id, "reported")
        self.assertEqual(catalog.models[0].default_reasoning_effort, "low")
        with self.assertRaises(ValidationError):
            ModelCatalog(models=catalog.models, default_model_id="missing")
        with self.assertRaises(ValidationError):
            ModelCatalog(models=catalog.models + catalog.models)
        with self.assertRaises(ValidationError):
            ModelOption(
                id="reported",
                reasoning_efforts=["low"],
                default_reasoning_effort="high",
            )

    def test_default_omission_sentinel_is_not_a_native_default(self):
        """An existing default execution setting does not identify a native effort."""
        model = ModelOption.from_payload({"id": "native", "efforts": ["default"]})
        self.assertEqual(model.reasoning_efforts, ["default"])
        self.assertIsNone(model.default_reasoning_effort)

    def test_missing_snapshot_does_not_discover_or_invent_choices(self):
        """A cold observation is None for every provider, without native effects."""
        for catalog in self.catalogs():
            with self.subTest(catalog=type(catalog).__name__):
                self.assertIsInstance(catalog, BaseModelCatalog)
                self.assertIsNone(catalog.snapshot())
                self.assertTrue(catalog.wait_until_idle(timeout=0))
                catalog.agent._model_catalog.assert_not_called()
                catalog.agent._discover_models.assert_not_called()

    def test_snapshot_is_detached_and_does_not_require_freshness(self):
        """Dispatch can inspect old observed choices without selecting or refreshing."""
        for catalog in self.catalogs():
            with self.subTest(catalog=type(catalog).__name__):
                native = {
                    "models": [{"id": "native-choice", "efforts": ["low"]}],
                    "submitted_turns": 0,
                }
                catalog._cached = (0.0, native)
                snapshot = catalog.snapshot()
                self.assertEqual(snapshot.to_payload(), native)
                snapshot.models[0].reasoning_efforts.append("changed-by-caller")
                self.assertEqual(native["models"][0]["efforts"], ["low"])
                self.assertEqual(catalog._cached[0], 0.0)

    def test_wait_observes_serialized_discovery(self):
        """A held discovery lock cannot be mistaken for an idle provider."""
        for catalog in self.catalogs():
            with self.subTest(catalog=type(catalog).__name__):
                catalog._lock.acquire()
                try:
                    self.assertFalse(catalog.wait_until_idle(timeout=0))
                finally:
                    catalog._lock.release()
                self.assertTrue(catalog.wait_until_idle(timeout=0))

    def test_wait_observes_shared_future_after_lock_is_released(self):
        """Claude-style shared discovery remains active outside the cache mutex."""
        for catalog in self.catalogs():
            with self.subTest(catalog=type(catalog).__name__):
                pending = catalog._pending = Future()
                self.assertFalse(catalog.wait_until_idle(timeout=0))
                pending.set_result({"models": []})
                self.assertTrue(catalog.wait_until_idle(timeout=0))
                self.assertIsNone(catalog.snapshot())

    def test_failed_discovery_completion_is_not_a_catalogue_success(self):
        """Waiting reports completion while the cache remains absent or unchanged."""
        for catalog in self.catalogs():
            with self.subTest(catalog=type(catalog).__name__):
                pending = catalog._pending = Future()
                pending.set_exception(ValueError("native discovery failed"))
                self.assertTrue(catalog.wait_until_idle(timeout=0))
                self.assertIsNone(catalog.snapshot())
