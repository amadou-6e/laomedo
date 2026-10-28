"""Error types for skills / ingestion."""

from __future__ import annotations


class BundleIngestError(RuntimeError):
    """An incoming bundle failed identity, policy, size or integrity checks.

    ``code`` identifies the refusal before the bundle becomes a trusted
    staged commit. Partially inspected data is not a verified bundle."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)
