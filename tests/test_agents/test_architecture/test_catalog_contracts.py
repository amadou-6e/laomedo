"""Exercise one cache-observation contract against each actual provider catalogue."""

from concurrent.futures import Future
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from laomedo.agents.agents.base.interim import BaseModelCatalog
from laomedo.agents.agents.codex.catalog import CodexModelCatalog
from laomedo.agents.agents.claude.catalog import ClaudeModelCatalog
from laomedo.agents.agents.opencode.catalog import OpenCodeModelCatalog


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
                self.assertEqual(snapshot.model_dump(exclude_unset=True), native)
                snapshot.models[0].efforts.append("changed-by-caller")
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
