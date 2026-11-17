"""Nonexecuting catalog checks with real native group expansion and synthetic code."""

from copy import deepcopy
from importlib.util import find_spec
import unittest

from pydantic import ValidationError

if find_spec("lfx") is None:
    raise unittest.SkipTest("Optional native graph expansion is not installed")

from laomedo.github.connections.errors import GitHubNodeAuthorizationError
from laomedo.integrations.langflow.authentication.catalog import GitHubGraphCatalog


class GitHubGraphCatalogTests(unittest.TestCase):
    """Canonical identity plus exact source is required for every constructed node."""

    def setUp(self):
        self.code = "raise RuntimeError('catalog checks must not execute Python')"
        self.registry = {
            "Laomedo": {"LaomedoGitHubPR": {"template": {"code": {"value": self.code}}}}
        }
        self.catalog = GitHubGraphCatalog.capture(self.registry)
        self.node = {
            "id": "pr-1",
            "data": {
                "id": "pr-1",
                "type": "LaomedoGitHubPR",
                "node": {
                    "template": {
                        "code": {
                            "name": "code",
                            "value": self.code,
                            "show": False,
                            "advanced": True,
                        }
                    }
                },
            },
        }
        self.graph = {"nodes": [self.node], "edges": []}

    def group(self, template=None):
        return {
            "nodes": [
                {
                    "id": "group-1",
                    "data": {
                        "id": "group-1",
                        "type": "group",
                        "node": {
                            "template": template or {},
                            "flow": {"data": deepcopy(self.graph)},
                        },
                    },
                }
            ],
            "edges": [],
        }

    def test_exact_catalog_source_is_checked_without_executing_it(self):
        effective = self.catalog.effective_graph(self.graph)
        self.assertEqual(effective, self.graph)
        self.assertIsNot(effective, self.graph)

    def test_namespaced_identity_comes_from_host_entry_not_posted_legacy_label(self):
        identity = "ext:laomedo:LaomedoGitHubPR@extra"
        component = deepcopy(self.registry["Laomedo"]["LaomedoGitHubPR"])
        component.update(name="LaomedoGitHubPR", namespaced_id=identity)
        catalog = GitHubGraphCatalog.capture({"Laomedo": {identity: component}})
        graph = deepcopy(self.graph)
        graph["nodes"][0]["data"]["type"] = identity
        catalog.effective_graph(graph)
        with self.assertRaises(GitHubNodeAuthorizationError):
            catalog.effective_graph(self.graph)

    def test_forged_display_name_or_hash_does_not_admit_edited_code(self):
        for change in ("type", "code"):
            graph = deepcopy(self.graph)
            data = graph["nodes"][0]["data"]
            data["node"]["name"] = "LaomedoGitHubPR"
            data["node"]["metadata"] = {
                "code_hash": self.catalog.snapshot.entries[0].code_digest
            }
            if change == "type":
                data["type"] = "CustomNode"
            else:
                data["node"]["template"]["code"]["value"] += "\n# edited"
            with self.assertRaises(GitHubNodeAuthorizationError):
                self.catalog.effective_graph(graph)

    def test_unclassified_runtime_code_and_flow_loaders_are_not_implicitly_trusted(
        self,
    ):
        for kind in (
            "PythonREPLComponent",
            "RunFlow",
            "SubFlow",
            "FlowTool",
            "NewCatalogType",
        ):
            registry = deepcopy(self.registry)
            registry["Laomedo"][kind] = deepcopy(registry["Laomedo"]["LaomedoGitHubPR"])
            catalog = GitHubGraphCatalog.capture(registry)
            graph = deepcopy(self.graph)
            graph["nodes"][0]["data"]["type"] = kind
            with self.assertRaises(GitHubNodeAuthorizationError):
                catalog.effective_graph(graph)

    def test_nested_groups_expand_with_native_function_and_preserve_input(self):
        graph = self.group()
        original = deepcopy(graph)
        effective = self.catalog.effective_graph(graph)
        self.assertEqual([node["id"] for node in effective["nodes"]], ["pr-1"])
        self.assertEqual(graph, original)

    def test_unknown_disconnected_or_nested_leaf_is_refused(self):
        unknown = deepcopy(self.node)
        unknown["id"] = "disconnected"
        unknown["data"]["type"] = "CustomNode"
        for graph in (deepcopy(self.graph), self.group()):
            if graph["nodes"][0]["data"]["node"].get("flow"):
                graph["nodes"][0]["data"]["node"]["flow"]["data"]["nodes"].append(
                    unknown
                )
            else:
                graph["nodes"].append(unknown)
            with self.assertRaises(GitHubNodeAuthorizationError):
                self.catalog.effective_graph(graph)

    def test_group_proxy_cannot_replace_child_python_after_validation(self):
        graph = self.group(
            {
                "override": {
                    "proxy": {"field": "code", "id": "pr-1"},
                    "value": "edited Python",
                }
            }
        )
        with self.assertRaises(GitHubNodeAuthorizationError):
            self.catalog.effective_graph(graph)

    def test_registry_reload_cannot_change_an_existing_snapshot(self):
        self.registry["Laomedo"]["LaomedoGitHubPR"]["template"]["code"][
            "value"
        ] = "new code"
        self.catalog.effective_graph(self.graph)
        with self.assertRaises(ValidationError):
            self.catalog.snapshot.entries[0].code_digest = "0" * 64
        reloaded = GitHubGraphCatalog.capture(self.registry)
        with self.assertRaises(GitHubNodeAuthorizationError):
            reloaded.effective_graph(self.graph)

    def test_empty_or_ambiguous_catalog_fails_closed(self):
        for registry in (
            {},
            {"other": {}},
            {
                **self.registry,
                "collision": {
                    "LaomedoGitHubPR": {
                        "template": {"code": {"value": "different code"}}
                    }
                },
            },
        ):
            with self.assertRaises(GitHubNodeAuthorizationError):
                GitHubGraphCatalog.capture(registry)
