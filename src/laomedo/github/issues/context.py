"""Read-only selected-issue context for the EXP-02 integration probe.

Timeline cross-references are candidates, not an exhaustive PR search and never
authorization to update a PR. All GitHub calls are reads through the existing
``gh`` login; no credentials or raw command errors enter the returned record."""

from __future__ import annotations

import laomedo.github.issues.utils as _issues_utils

if __name__ == "__main__":
    raise SystemExit(_issues_utils.main())
