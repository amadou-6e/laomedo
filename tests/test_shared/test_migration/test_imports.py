"""Maintained callers import the current module and symbol owners."""

import unittest

from support.import_contracts import retired_imports
from support.paths import repository_root
from test_shared.test_migration.utils import load_migration


class MaintainedImportTests(unittest.TestCase):
    def test_maintained_sources_and_embedded_graph_code_use_current_owners(self):
        migration = load_migration()
        self.assertEqual(
            retired_imports(
                repository_root(), migration.MODULE_PATHS, migration.SYMBOL_PATHS
            ),
            [],
        )
