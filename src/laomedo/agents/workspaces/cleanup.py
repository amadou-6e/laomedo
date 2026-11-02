"""Remove only disposable working trees inside an Agent's owned run state."""

from __future__ import annotations

from pathlib import Path
import shutil
import stat

from laomedo.agents.workspaces.skills.errors import WorkspaceSkillError
from laomedo.skills.registry.files import is_link


def remove_owned_tree(path: Path, state: Path) -> None:
    root = path.resolve()
    if (
        root == state.resolve()
        or not root.is_relative_to(state.resolve())
        or is_link(path)
    ):
        raise WorkspaceSkillError("cleanup_path_outside_run_state")

    def readonly_retry(operation, item, error):
        target = Path(item)
        if (
            not isinstance(error[1], PermissionError)
            or not target.resolve().is_relative_to(root)
            or is_link(target)
        ):
            raise error[1]
        target.chmod(target.stat().st_mode | stat.S_IWRITE)
        operation(item)

    shutil.rmtree(path, onerror=readonly_retry)
