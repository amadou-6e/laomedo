"""Error types for host / publication / bundle."""

from __future__ import annotations


class BundleStageError(RuntimeError):
    """Bundle staging was refused before bounded container dispatch.

    ``code`` records the failed prerequisite. The bundle is not established
    as a trusted staged commit and must not be published."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
