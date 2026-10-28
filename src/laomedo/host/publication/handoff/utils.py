"""Implementation owned by host / publication / handoff / utils."""

from __future__ import annotations

import json


def _deny(code):
    import laomedo.host.mediation.errors as _mediation_errors

    raise _mediation_errors.MediationError(code)


def _json(value):
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    )
