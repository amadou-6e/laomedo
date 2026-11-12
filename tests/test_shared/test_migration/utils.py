"""Read owner maps used by current import checks and retained evidence controls."""

import json
from types import SimpleNamespace
from support.paths import repository_root


def load_owner_maps():
    """Read static ownership data without loading a source-rewriting tool."""
    root = repository_root() / "tools/migrations"
    return SimpleNamespace(
        MODULE_PATHS=json.loads((root / "module-paths.json").read_text()),
        SYMBOL_PATHS=json.loads((root / "symbol-paths.json").read_text()),
    )
