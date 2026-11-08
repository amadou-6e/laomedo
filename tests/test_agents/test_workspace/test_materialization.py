"""Real local Git/registry controls; no Docker or provider request is performed."""

from pathlib import Path
import tempfile
import unittest

from laomedo.agents.agents.codex.agent import CodexAgent as CodexRunner
from laomedo.agents.errors import RunnerError
from laomedo.agents.workspaces.utils import _hash_tree
from laomedo.git.models import GitEnvironmentProfile, GitExecutionContext
from laomedo.git.repository import GitRepository
from laomedo.skills.registry.errors import SkillStoreError
from laomedo.skills.registry.store import SkillStore
from laomedo.skills.registry.files import inventory
from laomedo.skills.registry.hashing import tree_hash
from laomedo.agents.workspaces.skills.utils import install
from laomedo.agents.workspaces.cleanup import remove_owned_tree
from laomedo.agents.workspaces.skills.utils import verify


class SkillMaterializationTests(unittest.TestCase):
    """Own isolated resources and keep the historical assertions executable."""

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        home = self.root / "git-home"
        home.mkdir()
        self.context = GitExecutionContext(
            profile=GitEnvironmentProfile.WORKSPACE, home=home, hardened=True
        )

    def git(self, directory, *arguments):
        """Execute bounded local Git with private configuration; fail on errors."""
        result = GitRepository(directory, context=self.context).run(
            list(arguments),
            configuration=(
                ("core.autocrlf", "true"),
                ("protocol.file.allow", "always"),
                ("user.name", "Skill test"),
                ("user.email", "skill-test@example.invalid"),
                ("commit.gpgsign", "false"),
            ),
        )
        result.check_returncode()
        return result.stdout

    def prepare(self, ending):
        """Create a fresh exact-byte Skill and source repository under this test."""
        self.case = self.root / ending.hex()
        repository = self.case / "repository"
        source = repository / "source"
        source.mkdir(parents=True)
        (source / "task.txt").write_bytes(b"source task\n")
        self.git(repository, "init", "--quiet", "--template=")
        self.git(repository, "add", ".")
        self.git(repository, "commit", "--quiet", "-m", "Source baseline")
        self.repository = repository
        self.source = self.case / "skill"
        self.source.mkdir()
        self.content = ending.join(
            [b"---", b"name: materialized-skill", b"---", b"Fixed instructions.", b""]
        )
        (self.source / "SKILL.md").write_bytes(self.content)
        (self.source / "notes.txt").write_bytes(b"fixed bytes\r\n")
        self.store = SkillStore(self.case / "registry")
        self.reference = self.store.import_skill("materialized-skill", self.source)
        self.runner = CodexRunner(
            self.case / "state", self.store.root, source, check_docker=False
        )

    def test_exact_byte_revisions_and_git_edit_isolation(self):
        revisions = []
        for ending in (b"\n", b"\r\n"):
            with self.subTest(line_ending=ending):
                self.prepare(ending)
                revisions.append(self.reference["revision_id"])
                source_hash = _hash_tree(self.repository, exclude_root_git=True)
                self.assertEqual(
                    self.git(self.repository, "status", "--porcelain"), b""
                )
                for protected in (False, True):
                    workspace = self.case / (
                        "protected" if protected else "unprotected"
                    )
                    self.git(
                        self.case,
                        "clone",
                        "--no-hardlinks",
                        "--quiet",
                        str(self.repository),
                        str(workspace),
                    )
                    self.assertEqual(
                        (workspace / "source/task.txt").read_bytes(), b"source task\r\n"
                    )
                    self.assertEqual(
                        self.git(workspace, "show", "HEAD:source/task.txt"),
                        b"source task\n",
                    )
                    before = _hash_tree(workspace, exclude_root_git=True)
                    exclusion = (
                        install(workspace, [self.reference]) if protected else None
                    )
                    self.assertEqual(self.git(workspace, "status", "--porcelain"), b"")
                    offered = self.runner._materialize(workspace, self.reference)
                    delivered = workspace / ".agents/skills/materialized-skill"
                    self.assertEqual(inventory(delivered), inventory(self.source))
                    self.assertEqual(
                        (delivered / "SKILL.md").read_bytes(), self.content
                    )
                    self.assertEqual(
                        tree_hash(inventory(delivered)), self.reference["tree_hash"]
                    )
                    self.assertEqual(offered["use_evidence"], "offered")
                    status = self.git(
                        workspace, "status", "--porcelain", "--untracked-files=all"
                    )
                    clean = self.git(workspace, "clean", "-nd")
                    self.git(workspace, "add", "-A")
                    staged = self.git(workspace, "diff", "--cached", "--name-only")
                    if not protected:
                        self.assertIn(
                            b".agents/skills/materialized-skill/SKILL.md", status
                        )
                        self.assertIn(
                            b".agents/skills/materialized-skill/SKILL.md", staged
                        )
                        self.assertIn(b".agents/", clean)
                        self.assertEqual(
                            self.git(
                                workspace,
                                "show",
                                ":.agents/skills/materialized-skill/SKILL.md",
                            ),
                            self.content.replace(b"\r\n", b"\n"),
                        )
                        continue
                    self.assertEqual((status, staged, clean), (b"", b"", b""))
                    self.assertIn(
                        b".agents/skills/materialized-skill/",
                        self.git(
                            workspace,
                            "check-ignore",
                            "-v",
                            ".agents/skills/materialized-skill/SKILL.md",
                        ),
                    )
                    self.assertIn(b".agents/", self.git(workspace, "clean", "-ndx"))
                    verify(workspace, [self.reference], exclusion)
                    delivered_hash = _hash_tree(workspace, exclude_root_git=True)
                    self.assertNotEqual(before, delivered_hash)
                    (delivered / "SKILL.md").write_bytes(self.content + b"edited\n")
                    self.assertNotEqual(
                        tree_hash(inventory(delivered)), self.reference["tree_hash"]
                    )
                    self.assertNotEqual(
                        _hash_tree(workspace, exclude_root_git=True), delivered_hash
                    )
                    self.assertEqual(
                        (self.source / "SKILL.md").read_bytes(), self.content
                    )
                    self.assertEqual(
                        tree_hash(inventory(self.source)), self.reference["tree_hash"]
                    )
                    self.assertEqual(
                        self.store.read_file(
                            "materialized-skill",
                            self.reference["revision_id"],
                            "SKILL.md",
                        )["content"],
                        self.content,
                    )
                    self.assertEqual(
                        self.store.revision(
                            "materialized-skill", self.reference["revision_id"]
                        ),
                        self.reference,
                    )
                    self.assertEqual(self.git(workspace, "status", "--porcelain"), b"")
                    remove_owned_tree(workspace / ".agents", self.root)
                    self.assertEqual(self.git(workspace, "status", "--porcelain"), b"")
                self.assertEqual(
                    _hash_tree(self.repository, exclude_root_git=True), source_hash
                )
                self.assertEqual(
                    self.git(self.repository, "status", "--porcelain"), b""
                )
        self.assertNotEqual(*revisions)

    def test_parent_path_and_unsafe_id_are_rejected(self):
        for ending in (b"\n", b"\r\n"):
            with self.subTest(line_ending=ending):
                self.prepare(ending)
                with self.assertRaises(SkillStoreError):
                    self.store.read_file(
                        "materialized-skill",
                        self.reference["revision_id"],
                        "../SKILL.md",
                    )
                target = self.case / "unsafe-target"
                with self.assertRaises((RunnerError, SkillStoreError)):
                    self.runner._materialize(
                        target, {**self.reference, "skill_id": "../escape"}
                    )
                self.assertFalse(target.exists())

    def test_tampered_revision_is_rejected_before_materialization(self):
        for ending in (b"\n", b"\r\n"):
            with self.subTest(line_ending=ending):
                self.prepare(ending)
                bundle = (
                    self.store._revision_dir(
                        "materialized-skill", self.reference["revision_id"]
                    )
                    / "bundle/SKILL.md"
                )
                bundle.write_bytes(self.content + b"tampered\n")
                target = self.case / "tampered-target"
                with self.assertRaisesRegex(
                    SkillStoreError, "revision_integrity_failure"
                ):
                    self.runner._materialize(target, self.reference)
                self.assertFalse(target.exists())
