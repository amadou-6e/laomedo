"""Load the actual offline migration tool without persistent import-path changes."""

import importlib.util
import sys

from support.paths import repository_root


def load_migration():
    """Return the actual offline tool; propagate load errors and restore sys.path."""
    tool = repository_root() / "tools/migrations/migrate_module_paths.py"
    previous = sys.path[:]
    try:
        sys.path.insert(0, str(tool.parent))
        spec = importlib.util.spec_from_file_location(
            "module_path_migration_test", tool
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = previous
