"""Central access to Skills settings while submodules retain their definitions.

Constants are the original objects, not copies. Service settings classes have
explicit names to avoid collisions between their local Settings declarations.
Importing this module does not instantiate settings, load environment values or
read credential files; callers construct settings classes at the point of use.
"""

from laomedo.skills.interface.operations.settings import (
    Settings as OperationServiceSettings,
)
from laomedo.skills.interface.sources.settings import Settings as SourceServiceSettings
from laomedo.skills.operations.settings import MANUAL_ERROR_CODES
from laomedo.skills.registry.settings import ASSET_SUFFIXES
from laomedo.skills.registry.settings import HASH
from laomedo.skills.registry.settings import MAX_BUNDLE_BYTES
from laomedo.skills.registry.settings import MAX_DEPTH
from laomedo.skills.registry.settings import MAX_DIRECTORIES
from laomedo.skills.registry.settings import MAX_FILES
from laomedo.skills.registry.settings import MAX_FILE_BYTES
from laomedo.skills.registry.settings import NAME
from laomedo.skills.sources.settings import MAX_ENTRIES
from laomedo.skills.sources.settings import SECRET
from laomedo.skills.sources.settings import SKIP

__all__ = [
    "ASSET_SUFFIXES",
    "HASH",
    "MANUAL_ERROR_CODES",
    "MAX_BUNDLE_BYTES",
    "MAX_DEPTH",
    "MAX_DIRECTORIES",
    "MAX_ENTRIES",
    "MAX_FILES",
    "MAX_FILE_BYTES",
    "NAME",
    "OperationServiceSettings",
    "SECRET",
    "SKIP",
    "SourceServiceSettings",
]
