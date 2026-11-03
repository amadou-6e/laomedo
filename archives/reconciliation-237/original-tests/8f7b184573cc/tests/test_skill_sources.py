from pathlib import Path
from unittest.mock import patch
import json
import os
import subprocess
import tempfile
import threading
import unittest
import urllib.request
import urllib.error

from laomedo.skills.sources.service import SkillSources
from laomedo.skills.sources.errors import SourceError
from laomedo.skills.sources.bundle import validate_bundle
from laomedo.skills.interface.sources.server import SkillSourceServer as server
from laomedo.skills.interface.sources.client import source_request


class SkillSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.source.mkdir()
        for name in ("alpha", "beta"):
            folder = self.source / name
            folder.mkdir()
            (folder / "SKILL.md").write_text(
                f"---\nname: {name}\n---\n# {name}\n", encoding="utf-8"
            )
        self.resolver = SkillSources(
            self.root / "registry", self.root / "cache", [self.source]
        )

    def test_local_discovery_import_and_immutable_history(self):
        result = self.resolver.discover(self.source.as_uri())
        self.assertEqual([s["name"] for s in result["skills"]], ["alpha", "beta"])
        choice = result["skills"][0]["choice"]
        initial = self.resolver.revisions(str(self.source), choice)["revisions"][0]
        reference = self.resolver.resolve(str(self.source), choice, initial["choice"])
        self.assertEqual(reference["revision_id"], reference["tree_hash"])
        (self.source / "alpha/references").mkdir()
        (self.source / "alpha/references/new.md").write_text(
            "Second snapshot", encoding="utf-8"
        )
        later = self.resolver.revisions(str(self.source), choice)["revisions"]
        self.assertEqual(len(later), 2)
        self.assertNotEqual(later[0]["revision_id"], later[1]["revision_id"])
        self.assertEqual(
            self.resolver.resolve(str(self.source), choice, initial["choice"]),
            reference,
        )
        restarted = SkillSources(
            self.root / "registry", self.root / "cache", [self.source]
        )
        self.assertEqual(
            restarted.resolve(str(self.source), choice, initial["choice"]), reference
        )

    def test_registry_lists_exact_existing_revisions(self):
        choice = self.resolver.discover(str(self.source))["skills"][0]["choice"]
        imported = self.resolver.revisions(str(self.source), choice)["revisions"][0]
        source = str(self.resolver.store.root)
        self.assertEqual(self.resolver.discover(source)["skills"][0]["choice"], "alpha")
        revision = self.resolver.revisions(source, "alpha")["revisions"][0]
        self.assertTrue(revision["choice"].endswith(" | " + imported["revision_id"]))
        self.assertIn("local:", revision["choice"])

    def test_arbitrary_choices_and_outside_paths_are_refused(self):
        for source in (
            str(self.root),
            "relative/folder",
            "https://user:SECRET@github.com/o/r",
            "https://127.0.0.1/o/r",
            "https://github.com/o/r/tree/main",
        ):
            with self.subTest(source=source), self.assertRaises(SourceError):
                self.resolver.discover(source)
        with self.assertRaisesRegex(SourceError, "discovered_skill_required"):
            self.resolver.revisions(str(self.source), "made up")
        with self.assertRaisesRegex(SourceError, "discovered_revision_required"):
            self.resolver.resolve(str(self.source), "alpha", "latest")

    def test_secrets_links_and_script_execution(self):
        choice = self.resolver.discover(str(self.source))["skills"][0]["choice"]
        (self.source / "alpha/script.py").write_text(
            "raise RuntimeError('MUST-NOT-EXECUTE')"
        )
        self.resolver.revisions(str(self.source), choice)
        (self.source / "alpha/auth.json").write_text('"SECRET"')
        with self.assertRaisesRegex(SourceError, "source_bundle_unsafe"):
            self.resolver.revisions(str(self.source), choice)
        (self.source / "alpha/auth.json").unlink()
        try:
            (self.source / "outside").symlink_to(self.root, target_is_directory=True)
        except OSError:
            self.skipTest("Unprivileged symlinks unavailable")
        with self.assertRaisesRegex(SourceError, "local_source_unsafe"):
            self.resolver.discover(str(self.source))

    def test_git_branches_tags_and_pinned_prior_selection(self):
        def git(*args):
            return subprocess.check_output(
                ["git", "-C", str(self.source), *args], stderr=subprocess.DEVNULL
            )

        git("init", "-b", "main")
        git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "add",
            ".",
        )
        git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "first",
        )
        git("tag", "v1")
        (self.source / "alpha/SKILL.md").write_text(
            "---\nname: alpha\n---\n# Changed\n"
        )
        git("add", ".")
        git(
            "-c",
            "user.name=Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "second",
        )
        remote = SkillSources(
            self.root / "git-registry",
            self.root / "git-cache",
            repository_provider=lambda _: self.source,
        )
        source = "https://github.com/fixture/skills"
        choice = remote.discover(source)["skills"][0]["choice"]
        versions = remote.revisions(source, choice)["revisions"]
        self.assertEqual(len(versions), 2)
        self.assertTrue(any(v["choice"].startswith("heads/main @ ") for v in versions))
        self.assertTrue(any(v["choice"].startswith("tags/v1 @ ") for v in versions))
        old = next(v for v in versions if v["choice"].startswith("tags/"))
        git("tag", "-d", "v1")
        remote.discover(source)
        self.assertEqual(
            remote.resolve(source, choice, old["choice"])["revision_id"],
            old["revision_id"],
        )

    def test_authenticated_client_and_fixed_error_boundary(self):
        token = "fixture-token-" + "x" * 32
        service = server(self.resolver, token, port=0)
        thread = threading.Thread(target=service.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(service.server_close)
        self.addCleanup(service.shutdown)
        base = f"http://127.0.0.1:{service.server_address[1]}"
        request = urllib.request.Request(
            base + "/v1/skill-sources/discover",
            data=b"{}",
            headers={"Content-Type": "application/json"},
        )
        with self.assertRaises(urllib.error.HTTPError) as refused:
            urllib.request.urlopen(request)
        self.assertEqual(refused.exception.code, 401)
        path = self.root / "token"
        path.write_text(token)
        with patch.dict(
            os.environ,
            {
                "LAOMEDO_SKILL_SOURCE_URL": base,
                "LAOMEDO_SKILL_SOURCE_TOKEN_FILE": str(path),
            },
        ):
            result = source_request("discover", source=str(self.source))
            self.assertEqual(len(result["skills"]), 2)
            with self.assertRaisesRegex(ValueError, "source_discovery_failed"):
                source_request("discover", source="https://SECRET@example.invalid/o/r")
            with patch.dict(
                os.environ, {"LAOMEDO_SKILL_SOURCE_URL": "http://example.invalid"}
            ):
                with self.assertRaisesRegex(
                    ValueError, "source_service_not_configured"
                ):
                    source_request("discover", source=str(self.source))

    def test_windows_and_parent_paths_cannot_escape_import_staging(self):
        canary = self.root / "canary"
        canary.write_text("unchanged")
        for path in ("../canary", "C:/canary", "..\\canary", "/canary", "a/../canary"):
            with (
                self.subTest(path=path),
                self.assertRaisesRegex(SourceError, "source_bundle_unsafe"),
            ):
                self.resolver._register(
                    "alpha", {"SKILL.md": b"# fixture", path: b"changed"}, "fixture"
                )
        self.assertEqual(canary.read_text(), "unchanged")

    def test_git_does_not_inherit_personal_or_provider_configuration(self):
        captured = []
        original = subprocess.Popen

        def observe(*args, **kwargs):
            captured.append(kwargs["env"])
            return original(*args, **kwargs)

        with (
            patch.dict(
                os.environ,
                {
                    "OPENAI_API_KEY": "SECRET",
                    "GH_TOKEN": "SECRET",
                    "GIT_CONFIG_PARAMETERS": "SECRET",
                    "HOME": str(self.root),
                },
            ),
            patch("subprocess.Popen", side_effect=observe),
        ):
            self.resolver.repository_source._run(self.root, ["--version"])
        for name in ("OPENAI_API_KEY", "GH_TOKEN", "GIT_CONFIG_PARAMETERS", "HOME"):
            self.assertNotIn(name, captured[0])
        self.assertEqual(captured[0]["GIT_CONFIG_GLOBAL"], os.devnull)

    def test_portable_paths_refuse_aliases_before_staging(self):
        for files in (
            {"SKILL.md": b"skill", "A.md": b"a", "a.md": b"b"},
            {"SKILL.md": b"skill", "references": b"file", "references/a.md": b"child"},
            {"SKILL.md": b"skill", "CON.txt": b"device"},
            {"SKILL.md": b"skill", "references/a. ": b"alias"},
        ):
            with self.subTest(files=list(files)), self.assertRaises(SourceError):
                validate_bundle(files)

    def test_refused_option_overflow_does_not_import_or_change_index(self):
        choice = self.resolver.discover(str(self.source))["skills"][0]["choice"]
        self.resolver.revisions(str(self.source), choice)
        location = str(self.source)
        options = self.resolver.index[location]["revisions"][choice]
        reference = next(iter(options.values()))
        for number in range(63):
            options["historic-" + str(number)] = dict(reference)
        before = json.loads(json.dumps(self.resolver.index))
        folders = set((self.resolver.store._skill("alpha") / "revisions").iterdir())
        (self.source / "alpha/SKILL.md").write_text(
            "---\nname: alpha\n---\nnew bytes", encoding="utf-8"
        )
        with self.assertRaisesRegex(SourceError, "source_limit_exceeded"):
            self.resolver.revisions(location, choice)
        self.assertEqual(self.resolver.index, before)
        self.assertEqual(
            set((self.resolver.store._skill("alpha") / "revisions").iterdir()), folders
        )

    def test_same_named_source_revision_has_persistent_provenance(self):
        choice = self.resolver.discover(str(self.source))["skills"][0]["choice"]
        first = self.resolver.revisions(str(self.source), choice)["revisions"][0]
        original_latest = (
            self.resolver.store._skill("alpha") / "latest.json"
        ).read_bytes()
        other = self.source / "other"
        other.mkdir()
        (other / "SKILL.md").write_text(
            "---\nname: alpha\n---\nother source", encoding="utf-8"
        )
        self.resolver.discover(str(self.source))
        second = self.resolver.revisions(str(self.source), "alpha | other")[
            "revisions"
        ][0]
        registry = str(self.resolver.store.root)
        self.resolver.discover(registry)
        revisions = self.resolver.revisions(registry, "alpha")["revisions"]
        self.assertTrue(any("/ other |" in row["choice"] for row in revisions))
        self.assertEqual(
            (self.resolver.store._skill("alpha") / "latest.json").read_bytes(),
            original_latest,
        )
        self.assertNotEqual(first["revision_id"], second["revision_id"])
        restarted = SkillSources(
            self.resolver.store.root, self.root / "fresh-cache", [self.source]
        )
        restarted.discover(registry)
        self.assertTrue(
            any(
                "/ other |" in row["choice"]
                for row in restarted.revisions(registry, "alpha")["revisions"]
            )
        )

    def test_windows_crlf_frontmatter_preserves_original_bundle_bytes(self):
        data = b"---\r\nname: alpha\r\ndescription: Windows skill\r\n---\r\n# alpha\r\n"
        (self.source / "alpha/SKILL.md").write_bytes(data)
        choice = self.resolver.discover(str(self.source))["skills"][0]["choice"]
        self.assertEqual(choice, "alpha | alpha")
        revision = self.resolver.revisions(str(self.source), choice)["revisions"][0]
        bundle = (
            self.resolver.store._revision_dir("alpha", revision["revision_id"])
            / "bundle/SKILL.md"
        )
        self.assertEqual(bundle.read_bytes(), data)
        self.assertEqual(
            self.resolver.resolve(str(self.source), choice, revision["choice"])[
                "revision_id"
            ],
            revision["revision_id"],
        )
