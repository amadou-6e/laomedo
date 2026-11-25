"""The catalog exposes distinct source boundaries for local and repository Skills."""

import asyncio
import importlib.util
from copy import deepcopy
from pathlib import Path
from unittest import SkipTest
from unittest.mock import patch

import pytest

if (
    importlib.util.find_spec("lfx") is None
    or importlib.util.find_spec("langflow") is None
):
    raise SkipTest("Install Langflow to test its Skill components")

import langflow  # noqa: F401

from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template

from support.paths import repository_root
from laomedo.skills.sources.service import SkillSources

ROOT = repository_root()


def component(filename):
    code = (ROOT / "components" / "laomedo" / filename).read_text(encoding="utf-8")
    return build_custom_component_template(Component(_code=code))[1]


def test_langflow_discovers_distinct_skill_components():
    local = component("skill.py")
    remote = component("github_skill.py")
    assert local.name == "LaomedoLocalSkill"
    assert remote.name == "LaomedoGitHubSkill"
    assert "github_connection" not in {item.name for item in local.inputs}
    assert "github_connection" in {item.name for item in remote.inputs}


@pytest.mark.parametrize(
    ("filename", "source"),
    [
        ("skill.py", "https://github.com/owner/repo"),
        ("github_skill.py", "C:/some/local/folder"),
        ("github_skill.py", "https://example.org/owner/repo"),
    ],
)
def test_cross_boundary_sources_are_rejected_before_discovery(filename, source):
    node = component(filename)
    config = {item.name: item.to_dict() for item in node.inputs}
    result = asyncio.run(node.update_build_config(deepcopy(config), source, "source"))
    assert result["source"]["value"] == source
    assert "failed" in result["discovery_status"]["value"].lower()
    assert result["skill_id"]["options"] == []


@pytest.mark.parametrize(
    "source", ["https://github.com/owner/repo", "https://gitlab.com/owner/repo"]
)
def test_repository_component_accepts_supported_hosts(source):
    component("github_skill.py")._validate_source(source)


def test_local_component_accepts_local_source_and_registry_reference():
    node = component("skill.py")
    node._validate_source(str(Path.cwd()))
    node._validate_source("")


@pytest.mark.parametrize(
    ("filename", "source"),
    [
        ("skill.py", str(Path.cwd())),
        ("github_skill.py", "https://gitlab.com/owner/repo"),
    ],
)
def test_valid_sources_reach_the_shared_discovery_service(filename, source):
    node = component(filename)
    config = {item.name: item.to_dict() for item in node.inputs}
    with patch(
        "laomedo.skills.interface.langflow.component.source_request",
        return_value={"skills": [{"choice": "name | skills/name"}]},
    ) as request:
        result = asyncio.run(
            node.update_build_config(deepcopy(config), source, "source")
        )
    request.assert_called_once_with("discover", source=source)
    assert result["skill_id"]["options"] == ["name | skills/name"]


def test_private_github_does_not_fall_back_to_public_discovery():
    node = component("github_skill.py")
    config = {item.name: item.to_dict() for item in node.inputs}
    config["github_connection"]["value"] = "connected"
    with patch("laomedo.skills.interface.langflow.component.source_request") as request:
        asyncio.run(
            node.update_build_config(
                config, "https://github.com/owner/private", "source"
            )
        )
    request.assert_not_called()


def test_invalid_repository_clears_previous_private_selection():
    node = component("github_skill.py")
    config = {item.name: item.to_dict() for item in node.inputs}
    config["github_connection"]["value"] = "connected"
    config["private_repository_id"]["value"] = "previous-repository"
    result = asyncio.run(node.update_build_config(config, "C:/local", "source"))
    assert result["private_repository_id"]["value"] == ""


def test_local_skill_uses_current_files_without_revision_selection(tmp_path):
    source = tmp_path / "source"
    folder = source / "sample"
    folder.mkdir(parents=True)
    skill_file = folder / "SKILL.md"
    skill_file.write_text("---\nname: sample\n---\nfirst", encoding="utf-8")
    resolver = SkillSources(tmp_path / "registry", tmp_path / "state", [source])
    node = component("skill.py")
    config = {item.name: item.to_dict() for item in node.inputs}
    assert not config["revision_id"]["show"]
    assert not config["commit_id"]["show"]

    def request(action, **values):
        if action == "discover":
            return resolver.discover(values["source"])
        if action == "revisions":
            return resolver.revisions(values["source"], values["skill"])
        return resolver.resolve(values["source"], values["skill"], values["revision"])

    with patch(
        "laomedo.skills.interface.langflow.component.source_request",
        side_effect=request,
    ):
        config = asyncio.run(node.update_build_config(config, str(source), "source"))
        choice = config["skill_id"]["options"][0]
        config = asyncio.run(node.update_build_config(config, choice, "skill_id"))
        node.set(source=str(source), skill_id=choice)
        first = node.skill_output().data
        skill_file.write_text("---\nname: sample\n---\nsecond", encoding="utf-8")
        second = node.skill_output().data
        skill_file.write_text("---\nname: sample\n---\nfirst", encoding="utf-8")
        reverted = node.skill_output().data
        skill_file.unlink()
        with pytest.raises(ValueError):
            node.skill_output()
    assert first["revision_id"] != second["revision_id"]
    assert reverted == first
