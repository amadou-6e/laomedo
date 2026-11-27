"""Use real installed classes to verify startup-only metadata for the isolated mode."""

from pathlib import Path
import unittest
from unittest.mock import patch

from laomedo.integrations.langflow.execution.providers.catalog import (
    ProviderComponentCatalog,
)


class ProviderCatalogTests(unittest.TestCase):
    """Fixed installed metadata supplies both authoring and native source pins."""

    def test_fixed_catalog_contains_real_audited_component_sources_without_discovery(
        self,
    ):
        from laomedo.agents.connections.controllers import ProviderControllers

        root = Path(__file__).resolve().parents[4]
        with patch.object(
            ProviderControllers,
            "current",
            side_effect=AssertionError("startup must not discover accounts"),
        ):
            catalog = ProviderComponentCatalog(root / "components")
        classified = {
            entry.classification for entry in catalog.admission.snapshot.entries
        }
        self.assertTrue(
            {
                "LaomedoCodexAgent",
                "LaomedoClaudeAgent",
                "LaomedoGitHubIssue",
                "TextInput",
                "TextOutput",
            }
            <= classified
        )
        self.assertEqual(len(classified), 7)
