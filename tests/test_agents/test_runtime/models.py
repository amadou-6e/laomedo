"""Fresh, owned resources for credential-free Agent lifecycle controls."""

from contextlib import ExitStack
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from laomedo.agents.agents.codex.agent import CodexAgent
from laomedo.skills.registry.store import SkillStore
from test_agents.test_runtime.transport import FakeServer


class RunnerCase(BaseModel):
    """Own one isolated source, registry and runner; close only these resources."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    root: Path = Field(description="Private temporary root for this control.")
    source: Path = Field(description="Working input copied by the runner.")
    skill_source: Path = Field(
        description="Original Skill files for mutation and collision controls."
    )
    revision: dict = Field(description="Actual imported Skill registry receipt.")
    runner: CodexAgent = Field(
        exclude=True,
        repr=False,
        description="Internal runner using a transport double.",
    )
    _resources: ExitStack = PrivateAttr(default_factory=ExitStack)

    @classmethod
    def create(cls):
        resources = ExitStack()
        try:
            root = Path(resources.enter_context(TemporaryDirectory()))
            source = root / "source"
            source.mkdir()
            (source / "task.txt").write_text("source input")
            (root / ".git").mkdir()
            skill_source = root / "skill-source"
            skill_source.mkdir()
            (skill_source / "SKILL.md").write_text(
                "---\nname: sample\n---\nUse amber.\n"
            )
            store = SkillStore(root.parent / (root.name + "-skill-store"))
            resources.callback(shutil.rmtree, store.root, ignore_errors=True)
            resources.callback(shutil.rmtree, store.draft_root, ignore_errors=True)
            revision = store.import_skill("sample", skill_source)
            state = root.parent / (root.name + "-state")
            resources.callback(shutil.rmtree, state, ignore_errors=True)
            runner = CodexAgent(
                state, store.root, source, transport=FakeServer, check_docker=False
            )
            case = cls(
                root=root,
                source=source,
                skill_source=skill_source,
                revision=revision,
                runner=runner,
            )
            case._resources = resources
            return case
        except BaseException:
            resources.close()
            raise

    def request(self):
        return {
            "task": "Use the sample skill",
            "model": "test-model",
            "effort": "low",
            "skill_ref": {
                "skill_id": "sample",
                "revision_id": self.revision["revision_id"],
                "tree_hash": self.revision["tree_hash"],
            },
        }

    def close(self):
        self._resources.close()
