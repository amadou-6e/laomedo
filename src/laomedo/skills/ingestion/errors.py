"""Error types for skills / ingestion."""

from __future__ import annotations


class BundleIngestError(RuntimeError):
    """Typed refusal before a bundle becomes a trusted staged commit."""
