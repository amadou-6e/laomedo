"""Keep legacy and canonical imports bound to one module and globals."""
import importlib
import sys
from types import ModuleType


def alias_module(legacy_name: str, canonical_name: str) -> ModuleType:
    """Bind a retained import name to its defining module.

    Parameters
    ----------
    legacy_name : str
        Import retained for saved graphs or installed launchers.
    canonical_name : str
        Defining module under the current domain layout.

    Returns
    -------
    ModuleType
        The identical canonical module, including its mutable globals.
    """
    module = importlib.import_module(canonical_name)
    sys.modules[legacy_name] = module
    return module
