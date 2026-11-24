"""Install a narrow stale-editor fence for explicit graph file loads."""

from pathlib import Path


def apply_project_storage(checkout: Path):
    """Require existing Flow write guards and preserve all ordinary graph behavior."""
    path = (
        checkout / "src/backend/base/langflow/services/database/models/flow/guards.py"
    )
    text = path.read_text(encoding="utf-8")
    anchor = '    if getattr(flow, "locked", False) is not True:\n'
    if text.count(anchor) != 1 or "laomedo_storage_revision" in text:
        raise SystemExit("project_storage_flow_guard_anchor_missing")
    fence = """    # A file load starts a new editor epoch. Existing editor data retains its
    # old epoch and cannot autosave over the explicitly loaded graph. The
    # normal editor spreads flowData when saving, retaining this opaque value.
    if "data" in update_data:
        expected = (getattr(flow, "data", None) or {}).get("laomedo_storage_revision")
        incoming = update_data.get("data") or {}
        if expected and incoming.get("laomedo_storage_revision") != expected:
            raise LockedFlowError("This graph was loaded from a file. Reload the editor before saving.")
"""
    path.write_text(
        text.replace(anchor, fence + anchor)
        + "\n# Explicit capability checked before graph-file loading.\n"
        + "ensure_flow_update_allowed.laomedo_storage_fence = True\n",
        encoding="utf-8",
    )
