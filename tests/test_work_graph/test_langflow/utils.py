"""Runtime eligibility and graph field access for frozen-stage controls."""

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


def pinned_runtime_available():
    """Admit either pinned app distribution; the controls exercise its real APIs.

    Minimal app installs use langflow-base rather than the langflow umbrella.
    Every installed app distribution and lfx must match the pinned runtime.
    """
    try:
        if version("lfx") != "1.12.3":
            return False
    except PackageNotFoundError:
        return False
    installed_versions = []
    for distribution in ("langflow", "langflow-base"):
        try:
            installed_versions.append(version(distribution))
        except PackageNotFoundError:
            continue
    return bool(installed_versions) and all(
        installed_version == "1.12.3" for installed_version in installed_versions
    )


def field(flow, node_id, name):
    return next(node for node in flow["data"]["nodes"] if node["id"] == node_id)[
        "data"
    ]["node"]["template"][name]
