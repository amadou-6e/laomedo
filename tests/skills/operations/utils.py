"""Fresh operation setup shared by service and scheduler controls."""

from laomedo.skills.registry.store import SkillStore
from laomedo.skills.operations.service import SkillOperations
from skills.operations.models import SkillOperationCase


def make_operation_case(root):
    """Create the shared two-file scenario under a fresh caller-owned root."""
    source = root / "source"
    (source / "rules").mkdir(parents=True)
    original = "---\nname: internal-test\ndescription: Internal unit fixture.\n---\n"
    (source / "SKILL.md").write_bytes(original.encode())
    (source / "rules/one.md").write_bytes(b"original\n")
    store = SkillStore(root / "registry")
    initial = store.import_skill("internal-test", source)
    policy = {
        "policy_id": "test-policy",
        "revision_id": "1",
        "allowed_paths": ["SKILL.md", "rules/one.md", "rules/two.md"],
        "allowed_suffixes": [".md"],
        "allow_new_files": True,
        "allow_deletions": True,
        "allow_scripts": False,
        "allow_dependencies": False,
        "allow_assets": False,
        "required_frontmatter": ["name", "description"],
        "permitted_validation_commands": [],
        "max_files": 8,
        "max_file_bytes": 8192,
    }
    service = SkillOperations(store, root / "history.db", {"internal-test": policy})
    operation = {
        "action": "modify",
        "message": "Change two files together",
        "files": [
            {"path": "SKILL.md", "content": original + "\nUpdated.\n"},
            {"path": "rules/one.md", "content": "updated\n"},
        ],
    }

    return SkillOperationCase(
        root=root,
        original=original,
        store=store,
        initial=initial,
        policy=policy,
        service=service,
        operation=operation,
    )
