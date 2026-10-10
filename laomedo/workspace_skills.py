"""Exact run-local skill exclusions and immutable materialization validation."""
import hashlib
import os
import shutil
import stat
import tempfile
from pathlib import Path

from .skill_store import NAME, inventory, tree_hash, _is_link
from .git_workspace import _bounded_git, _git_environment, GitWorkspaceError


class WorkspaceSkillError(ValueError):
    pass


def _exclude(workspace: Path):
    git = workspace / '.git'
    if not git.exists():
        return None
    if not git.is_dir() or _is_link(git):
        raise WorkspaceSkillError('external_git_directory_unsupported')
    # Inspect entry metadata only, not Git object contents.
    for parent, dirs, names in os.walk(git, followlinks=False):
        for name in dirs + names:
            item = Path(parent) / name
            if _is_link(item) or not (item.is_dir() or item.is_file()) or (
                    item.is_file() and item.stat().st_nlink > 1):
                raise WorkspaceSkillError('unsafe_git_metadata')
    return git / 'info' / 'exclude'


def initialize(workspace: Path) -> None:
    """Create an independent baseline, never import host Git metadata or hooks."""
    if (workspace / '.git').exists():
        raise WorkspaceSkillError('workspace_git_metadata_conflict')
    with tempfile.TemporaryDirectory(prefix='laomedo-baseline-home-') as home:
        env = _git_environment(home)
        env.update(GIT_AUTHOR_DATE='2000-01-01T00:00:00+0000',
                   GIT_COMMITTER_DATE='2000-01-01T00:00:00+0000')
        prefix = ['git', '-C', str(workspace), '-c', 'core.autocrlf=false',
                  '-c', 'core.hooksPath=' + home, '-c', 'commit.gpgsign=false',
                  '-c', 'user.name=Laomedo Workspace',
                  '-c', 'user.email=workspace@example.invalid']
        for arguments in (['init', '--template='], ['add', '--force', '--all', '.'],
                          ['commit', '--allow-empty', '-m', 'Pinned source baseline']):
            try:
                result = _bounded_git(prefix + arguments, env)
            except (OSError, GitWorkspaceError):
                raise WorkspaceSkillError('workspace_git_initialization_failed') from None
            if result.returncode:
                raise WorkspaceSkillError('workspace_git_initialization_failed')
        # Git marks newly created loose objects read-only on Windows. These are
        # private baseline files, so allow ordinary disposable-fixture cleanup.
        for item in (workspace / '.git' / 'objects').rglob('*'):
            if item.is_file() and not _is_link(item):
                item.chmod(item.stat().st_mode | stat.S_IWRITE)


def remove_owned_tree(path: Path, state: Path) -> None:
    root = path.resolve()
    if root == state.resolve() or not root.is_relative_to(state.resolve()) or _is_link(path):
        raise WorkspaceSkillError('cleanup_path_outside_run_state')

    def readonly_retry(operation, item, error):
        target = Path(item)
        if not isinstance(error[1], PermissionError) or not target.resolve().is_relative_to(root) or _is_link(target):
            raise error[1]
        target.chmod(target.stat().st_mode | stat.S_IWRITE)
        operation(item)

    shutil.rmtree(path, onerror=readonly_retry)


def install(workspace: Path, skills: list[dict]) -> dict:
    for skill in skills:
        if not NAME.fullmatch(skill['skill_id']):
            raise WorkspaceSkillError('invalid_skill_id')
    exclude = _exclude(workspace)
    if exclude is None:
        return {'enabled': False}
    exclude.parent.mkdir(exist_ok=True)
    original = exclude.read_bytes() if exclude.exists() else b''
    rules = [f"/.agents/skills/{skill['skill_id']}/" for skill in skills]
    addition = '\n'.join(rules).encode('ascii') + b'\n'
    prefix = original + (b'\n' if original and not original.endswith(b'\n') else b'')
    exclude.write_bytes(prefix + addition)
    return {'enabled': True, 'rules': rules,
            'exclude_sha256': hashlib.sha256(exclude.read_bytes()).hexdigest()}


def verify(workspace: Path, skills: list[dict], exclusion: dict) -> None:
    for parent in (workspace / '.agents', workspace / '.agents' / 'skills'):
        if _is_link(parent) or not parent.is_dir():
            raise WorkspaceSkillError('unsafe_materialized_skill_path')
    if {entry.name for entry in (workspace / '.agents' / 'skills').iterdir()} != {
            skill['skill_id'] for skill in skills}:
        raise WorkspaceSkillError('unexpected_materialized_skill')
    for skill in skills:
        if not NAME.fullmatch(skill['skill_id']):
            raise WorkspaceSkillError('invalid_skill_id')
        if tree_hash(inventory(workspace / '.agents' / 'skills' / skill['skill_id'])) != skill['tree_hash']:
            raise WorkspaceSkillError('materialized_skill_mismatch')
    exclude = _exclude(workspace)
    if exclusion.get('enabled'):
        if exclude is None or not exclude.is_file() or hashlib.sha256(
                exclude.read_bytes()).hexdigest() != exclusion['exclude_sha256']:
            raise WorkspaceSkillError('skill_git_exclusion_changed')
    elif exclude is not None:
        raise WorkspaceSkillError('skill_git_exclusion_changed')
