"""Preserved frozen-graph runtime boundary controls."""

from copy import deepcopy
from datetime import datetime
from datetime import timedelta
from datetime import timezone
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
import time
import unittest
from unittest.mock import patch
from laomedo.integrations.langflow.stage_adapter import FrozenLangflowStage
from laomedo.work_graph.github import import_pages
from laomedo.work_graph.grants import LocalGrantAuthority
from laomedo.work_graph.launch import launch_github_saved_flow_stage
from laomedo.work_graph.launch import launch_work_stage
from laomedo.work_graph.runs.errors import LaunchError
from laomedo.work_graph.runs.store import WorkflowRunStore
from support.paths import repository_root

from test_work_graph.test_langflow.utils import field, pinned_runtime_available

FLOW = repository_root() / "tests/test_work_graph/fixtures/frozen-flow.json"


class LangflowRuntimeAdmissionTests(unittest.TestCase):
    """Metadata doubles check rejection categories, not real graph acceptance."""

    def test_runtime_distribution_admission_precedes_graph_construction(self):
        cases = (
            ({"langflow": "1.12.3", "lfx": "1.12.3"}, "unresolved_graph_identity"),
            (
                {"langflow-base": "1.12.3", "lfx": "1.12.3"},
                "unresolved_graph_identity",
            ),
            (
                {"langflow": "1.12.3", "langflow-base": "1.12.3", "lfx": "1.12.3"},
                "unresolved_graph_identity",
            ),
            ({}, "langflow_runtime_unavailable"),
            ({"lfx": "1.12.3"}, "langflow_runtime_unavailable"),
            ({"langflow": "1.12.3"}, "langflow_runtime_unavailable"),
            ({"langflow-base": "1.12.3"}, "langflow_runtime_unavailable"),
            ({"langflow": "1.12.2"}, "unsupported_langflow_revision"),
            ({"langflow-base": "1.12.2"}, "unsupported_langflow_revision"),
            (
                {"langflow": "1.12.3", "langflow-base": "1.12.2", "lfx": "1.12.3"},
                "unsupported_langflow_revision",
            ),
            (
                {"langflow": "1.12.2", "langflow-base": "1.12.3", "lfx": "1.12.3"},
                "unsupported_langflow_revision",
            ),
            (
                {"langflow-base": "1.12.3", "lfx": "1.12.2"},
                "unsupported_langflow_revision",
            ),
            (
                {"langflow": "1.12.3", "lfx": "1.12.2"},
                "unsupported_langflow_revision",
            ),
        )
        for installed, expected in cases:
            with self.subTest(installed=installed):

                def metadata_version(distribution):
                    if distribution not in installed:
                        raise PackageNotFoundError(distribution)
                    return installed[distribution]

                with patch(
                    "laomedo.integrations.langflow.stage_adapter.version",
                    side_effect=metadata_version,
                ):
                    with self.assertRaisesRegex(LaunchError, "^" + expected + "$"):
                        FrozenLangflowStage(None)
