"""Catalogue keys must not silently overwrite an earlier explanation."""

import json
import unittest
from support.paths import repository_root


class CatalogueShapeTests(unittest.TestCase):
    def test_catalogue_keys_are_unique(self):
        def unique(pairs):
            result = {}
            for key, value in pairs:
                self.assertNotIn(key, result, f"Duplicate error catalogue key: {key}")
                result[key] = value
            return result

        json.loads(
            (
                repository_root()
                / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text(encoding="utf-8"),
            object_pairs_hook=unique,
        )
