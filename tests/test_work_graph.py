"""Behavioral tests for source integrity and dependency inspection."""

import copy
from dataclasses import FrozenInstanceError, replace
import json
from pathlib import Path
import tempfile
import unittest

from laomedo.work_graph.github import fetch, import_pages
from laomedo.work_graph.model import Dependency, GraphSnapshot


FIXTURE = Path(__file__).parents[1] / "examples/work-graph/github-pages.json"
NOW = "2026-10-01T08:00:00+00:00"


def pages():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def connection(page):
    return page["data"]["repository"]["issues"]


class WorkGraphTests(unittest.TestCase):
    def test_roundtrip_hash_and_tamper(self):
        snapshot = import_pages("example/work", pages(), NOW)
        payload = json.loads(json.dumps(snapshot.to_dict()))
        self.assertEqual(GraphSnapshot.from_dict(payload), snapshot)
        payload["items"][0]["title"] = "changed"
        with self.assertRaisesRegex(ValueError, "digest"):
            GraphSnapshot.from_dict(payload)

    def test_refresh_retains_previous_artifact_and_stable_identity(self):
        first = import_pages("example/work", pages(), NOW)
        updated = pages()
        connection(updated[0])["nodes"][0]["title"] = "Revised title"
        second = import_pages("example/work", updated, "2026-10-01T09:00:00+00:00")
        with tempfile.TemporaryDirectory() as directory:
            first_path = first.save(Path(directory))
            original = first_path.read_bytes()
            self.assertNotEqual(first_path, second.save(Path(directory)))
            self.assertEqual(first_path.read_bytes(), original)
            self.assertEqual(first.save(Path(directory)), first_path)
        self.assertEqual(first.items[0].key, second.items[0].key)
        with self.assertRaises(FrozenInstanceError):
            first.items[0].title = "overwrite"

    def test_existing_corrupt_artifact_is_not_overwritten(self):
        snapshot = import_pages("example/work", pages(), NOW)
        with tempfile.TemporaryDirectory() as directory:
            path = snapshot.save(Path(directory))
            path.write_text("corrupt", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "differs"):
                snapshot.save(Path(directory))
            self.assertEqual(path.read_text(encoding="utf-8"), "corrupt")

    def test_isolated_label_match_is_preserved(self):
        graph = import_pages("example/work", pages(), NOW)
        projection = graph.project("open", ("notes",))
        self.assertEqual([item["number"] for item in projection["items"]], [3])
        self.assertEqual(projection["dependencies"], [])

    def test_filtered_blocker_still_controls_readiness(self):
        fixture = pages()
        connection(fixture[0])["nodes"][0]["state"] = "OPEN"
        graph = import_pages("example/work", fixture, NOW)
        projection = graph.project("open", ("adapter",))
        self.assertEqual(projection["items"][0]["readiness"], "blocked")
        self.assertEqual(len(projection["context_dependencies"]), 1)
        self.assertEqual(graph.readiness()["github:I_3"], "ready")

    def test_closed_blocker_makes_open_dependent_source_ready(self):
        graph = import_pages("example/work", pages(), NOW)
        self.assertEqual(graph.readiness()["github:I_2"], "ready")
        self.assertEqual(len(graph.dependencies), 1)  # both directions deduplicated

    def test_cross_repository_reference_remains_unresolved(self):
        fixture = pages()
        reference = connection(fixture[0])["nodes"][1]["blockedBy"]["nodes"][0]
        reference.update(id="EXTERNAL", url="https://github.com/other/work/issues/1")
        reference["repository"]["nameWithOwner"] = "other/work"
        graph = import_pages("example/work", fixture, NOW)
        self.assertEqual(graph.readiness()["github:I_2"], "unknown")
        self.assertTrue(any(edge.prerequisite_repository == "other/work"
                            for edge in graph.dependencies))

    def test_truncated_blockers_never_appear_ready(self):
        fixture = pages()
        connection(fixture[0])["nodes"][2]["blockedBy"]["totalCount"] = 101
        graph = import_pages("example/work", fixture, NOW)
        self.assertFalse(graph.source_complete)
        self.assertIn("dependencies_incomplete", graph.source_warnings)
        self.assertEqual(graph.readiness()["github:I_3"], "unknown")

    def test_cycles_and_downstream_nodes_are_distinguished(self):
        graph = import_pages("example/work", pages(), NOW)
        items = tuple(replace(item, state="OPEN") for item in graph.items)
        def edge(start, end):
            return Dependency(f"github:I_{start}", f"github:I_{end}",
                              f"https://github.com/example/work/issues/{start}",
                              f"https://github.com/example/work/issues/{end}",
                              "example/work", "example/work")
        graph = replace(graph, items=items, dependencies=tuple(sorted(
            (edge(1, 2), edge(2, 1), edge(2, 3)))))
        self.assertEqual(graph.cycle_keys(), frozenset(("github:I_1", "github:I_2")))
        self.assertEqual(graph.readiness()["github:I_3"], "blocked")
        self.assertEqual(graph.readiness()["github:I_1"], "cyclic")
        self_loop = replace(graph, dependencies=(edge(3, 3),))
        self.assertEqual(self_loop.cycle_keys(), frozenset(("github:I_3",)))

    def test_connector_fetches_all_pages(self):
        fixture = pages()[0]
        first, last = copy.deepcopy(fixture), copy.deepcopy(fixture)
        connection(first)["nodes"] = connection(first)["nodes"][:1]
        connection(first)["pageInfo"] = {"hasNextPage": True, "endCursor": "next"}
        connection(last)["nodes"] = connection(last)["nodes"][1:]
        calls = []
        def request(owner, name, cursor):
            calls.append((owner, name, cursor))
            return first if cursor is None else last
        graph = fetch("example/work", request)
        self.assertTrue(graph.source_complete)
        self.assertEqual(calls, [("example", "work", None), ("example", "work", "next")])

    def test_interrupted_fetch_retains_partial_items_with_unknown_readiness(self):
        fixture = pages()[0]
        connection(fixture)["nodes"] = connection(fixture)["nodes"][:1]
        connection(fixture)["pageInfo"] = {"hasNextPage": True, "endCursor": "next"}
        def request(owner, name, cursor):
            if cursor:
                raise RuntimeError("transport failure")
            return fixture
        graph = fetch("example/work", request)
        self.assertFalse(graph.source_complete)
        self.assertEqual(len(graph.items), 1)
        self.assertIn("fetch_error", graph.source_warnings)
        fixture = pages()
        connection(fixture[0])["pageInfo"] = {"hasNextPage": True, "endCursor": "next"}
        graph = import_pages("example/work", fixture, NOW)
        self.assertEqual(graph.readiness()["github:I_3"], "unknown")

    def test_wrong_repository_conflicting_items_and_pagination_fail(self):
        with self.assertRaisesRegex(ValueError, "does not match"):
            import_pages("wrong/work", pages(), NOW)
        fixture = pages()
        duplicate = copy.deepcopy(connection(fixture[0])["nodes"][0])
        duplicate["body"] = "conflicting update"
        connection(fixture[0])["nodes"].append(duplicate)
        with self.assertRaisesRegex(ValueError, "Conflicting snapshots"):
            import_pages("example/work", fixture, NOW)
        fixture = pages()[0]
        connection(fixture)["pageInfo"] = {"hasNextPage": True, "endCursor": "repeated"}
        with self.assertRaisesRegex(ValueError, "repeated"):
            fetch("example/work", lambda *args: fixture)


if __name__ == "__main__":
    unittest.main()
