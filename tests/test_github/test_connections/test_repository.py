"""Bounded object-reader controls against synthetic GitHub JSON, not live acceptance."""

import base64
from hashlib import sha1
from importlib.util import find_spec
from time import monotonic
import unittest
from uuid import uuid4

if find_spec("httpx2") is None:
    raise unittest.SkipTest("Optional private-source HTTPX2 is not installed")

from httpx2 import MockTransport, Response
from pydantic import SecretStr

from laomedo.github.connections.client import GitHubReadClient
from laomedo.github.connections.errors import GitHubRepositoryAccessError
from laomedo.github.connections.models import (
    GitHubConnectionCredential,
    GitHubPrincipal,
    GitHubReadAuthorization,
    GitHubRepositoryIdentity,
)
from laomedo.github.connections.repository import GitHubRepositoryReader
from laomedo.github.connections.settings import (
    GITHUB_READ_TOTAL_BYTES,
    GITHUB_TAG_DEPTH,
)
from laomedo.skills.registry.settings import MAX_FILE_BYTES
from laomedo.skills.sources.errors import SourceError
from laomedo.skills.sources.models import SkillRepositoryEntry


class GitHubRepositoryReaderTests(unittest.IsolatedAsyncioTestCase):
    """Use actual HTTPX2 and canonical Skill validators without private credentials."""

    async def asyncSetUp(self):
        self.commit, self.tree = "1" * 40, "2" * 40
        self.prefix = "/repos/synthetic/private/git/"
        self.responses, self.requests = {}, []
        self.paths = {}
        for path, content in {
            "skill/SKILL.md": b"---\nname: private-skill\ndescription: Synthetic only.\n---\n\nInstructions.\n",
            "skill/guide.md": b"Guide\r\nexact bytes\n",
        }.items():
            oid = sha1(
                b"blob " + str(len(content)).encode() + b"\0" + content
            ).hexdigest()
            self.paths[path] = {
                "path": path,
                "mode": "100644",
                "type": "blob",
                "sha": oid,
                "size": len(content),
            }
            self.responses["blobs/" + oid] = {
                "sha": oid,
                "encoding": "base64",
                "size": len(content),
                "content": base64.b64encode(content).decode() + "\n",
            }
        self.responses.update(
            {
                "matching-refs/heads/": [
                    {
                        "ref": "refs/heads/main",
                        "object": {"type": "commit", "sha": self.commit},
                    }
                ],
                "matching-refs/tags/": [],
                "commits/"
                + self.commit: {"sha": self.commit, "tree": {"sha": self.tree}},
                "trees/"
                + self.tree: {
                    "sha": self.tree,
                    "truncated": False,
                    "tree": list(self.paths.values()),
                },
            }
        )
        credential = GitHubConnectionCredential.from_token(
            SecretStr("github_pat_synthetic")
        )
        self.client = GitHubReadClient(
            credential, transport=MockTransport(self.respond)
        )
        self.addAsyncCleanup(self.client.close)
        authorization = GitHubReadAuthorization(
            owner_id=uuid4(),
            connection_id=uuid4(),
            generation=1,
            principal=GitHubPrincipal(id=123, login="synthetic"),
            repository=GitHubRepositoryIdentity(
                id=456, full_name="synthetic/private", private=True
            ),
            deadline=monotonic() + 60,
        )
        self.reader = GitHubRepositoryReader(authorization, self.client)

    def respond(self, request):
        """Serve only synthetic fixed-origin GETs; never download a provider URL."""
        self.assertEqual((request.method, request.url.host), ("GET", "api.github.com"))
        path = request.url.path.removeprefix(self.prefix)
        self.requests.append(path)
        value = self.responses[path]
        return value if isinstance(value, Response) else Response(200, json=value)

    async def test_discovery_and_exact_bundle_reuse_canonical_models(self):
        choices = await self.reader.discover()
        self.assertEqual(
            [(item.name, item.path) for item in choices], [("private-skill", "skill")]
        )
        revisions = await self.reader.revisions(choices[0])
        self.assertEqual(len(revisions), 1)
        self.assertEqual(revisions[0].commit, self.commit)
        self.assertEqual(
            revisions[0].candidate.files["guide.md"], b"Guide\r\nexact bytes\n"
        )
        self.assertNotIn("Instructions", revisions[0].candidate.model_dump_json())
        instruction_id = self.paths["skill/SKILL.md"]["sha"]
        self.assertEqual(self.requests.count("blobs/" + instruction_id), 1)
        self.assertEqual(self.requests.count("trees/" + self.tree), 1)

    async def test_ref_limit_and_unfinished_pagination_refuse_before_tree_reads(self):
        self.responses["matching-refs/heads/"] = [
            {
                "ref": f"refs/heads/b{index}",
                "object": {"type": "commit", "sha": self.commit},
            }
            for index in range(33)
        ]
        with self.assertRaises(SourceError):
            await self.reader.refs()
        self.assertFalse(any(path.startswith("commits/") for path in self.requests))
        self.responses["matching-refs/heads/"] = Response(
            200, json=[], headers={"Link": '<https://evil.invalid/?page=2>; rel="next"'}
        )
        with self.assertRaises(SourceError):
            await self.reader.refs()

    async def test_only_exact_heads_and_tags_namespaces_are_admitted(self):
        self.responses["matching-refs/heads/"][0]["ref"] = "refs/notes/hidden"
        with self.assertRaises(SourceError):
            await self.reader.refs()

    async def test_annotated_tag_peeling_binds_echoes_and_refuses_cycles(self):
        tag = "3" * 40
        self.responses["matching-refs/tags/"] = [
            {"ref": "refs/tags/v1", "object": {"type": "tag", "sha": tag}}
        ]
        self.responses["tags/" + tag] = {
            "sha": tag,
            "object": {"type": "commit", "sha": self.commit},
        }
        refs = await self.reader.refs()
        self.assertEqual(refs[1].commit, self.commit)
        self.reader.references = None
        self.responses["tags/" + tag]["object"] = {"type": "tag", "sha": tag}
        with self.assertRaises(SourceError):
            await self.reader.refs()

    async def test_tag_depth_is_finite(self):
        tags = [f"{index + 100:040x}" for index in range(GITHUB_TAG_DEPTH + 1)]
        self.responses["matching-refs/tags/"] = [
            {"ref": "refs/tags/deep", "object": {"type": "tag", "sha": tags[0]}}
        ]
        for index, tag in enumerate(tags):
            self.responses["tags/" + tag] = {
                "sha": tag,
                "object": {
                    "type": "tag" if index + 1 < len(tags) else "commit",
                    "sha": tags[index + 1] if index + 1 < len(tags) else self.commit,
                },
            }
        with self.assertRaises(SourceError):
            await self.reader.refs()
        self.assertEqual(
            len([path for path in self.requests if path.startswith("tags/")]),
            GITHUB_TAG_DEPTH,
        )

    async def test_recursive_truncation_and_mismatched_commit_refuse(self):
        self.responses["trees/" + self.tree]["truncated"] = True
        with self.assertRaises(SourceError):
            await self.reader.entries(self.commit)
        self.responses["trees/" + self.tree]["truncated"] = False
        self.responses["commits/" + self.commit]["sha"] = "9" * 40
        with self.assertRaises(SourceError):
            await self.reader.entries(self.commit)

    async def test_links_submodules_and_unsafe_paths_refuse(self):
        for change in (
            {"mode": "120000"},
            {"mode": "160000", "type": "commit"},
            {"path": "../escape"},
            {"path": "folder\\escape"},
        ):
            self.responses["trees/" + self.tree]["tree"] = [
                {**self.paths["skill/SKILL.md"], **change}
            ]
            with self.subTest(), self.assertRaises(SourceError):
                await self.reader.entries(self.commit)

    async def test_duplicate_tree_paths_refuse(self):
        self.responses["trees/" + self.tree]["tree"] = [
            self.paths["skill/SKILL.md"]
        ] * 2
        with self.assertRaises(SourceError):
            await self.reader.entries(self.commit)

    async def test_blob_identity_base64_size_and_mode_are_checked(self):
        path = self.paths["skill/SKILL.md"]
        entry = SkillRepositoryEntry(mode="100644", kind="blob", object_id=path["sha"])
        original = dict(self.responses["blobs/" + path["sha"]])
        for change in (
            {"size": MAX_FILE_BYTES + 1},
            {"content": "%not-base64"},
            {"size": 1},
            {"content": base64.b64encode(b"altered").decode(), "size": 7},
            {"sha": "9" * 40},
        ):
            self.responses["blobs/" + path["sha"]] = {**original, **change}
            with self.subTest(), self.assertRaises(SourceError):
                await self.reader.read_blob(entry)
        with self.assertRaises(SourceError):
            await self.reader.read_blob(entry.model_copy(update={"mode": "120000"}))

    async def test_cached_objects_cannot_bypass_total_deadline(self):
        await self.reader.discover()
        self.client.deadline = monotonic() - 1
        with self.assertRaises(SourceError):
            await self.reader.discover()

    async def test_total_http_byte_budget_is_not_reset_by_each_blob(self):
        self.client.read_bytes = GITHUB_READ_TOTAL_BYTES - 1
        with self.assertRaises(GitHubRepositoryAccessError):
            await self.reader.discover()

    async def test_secret_paths_are_refused_before_a_bundle_is_returned(self):
        choices = await self.reader.discover()
        entries = self.reader.trees[self.commit]
        entries["skill/.env"] = entries["skill/guide.md"]
        with self.assertRaises(SourceError):
            await self.reader.revisions(choices[0])
