"""Pinned whole-skill reference for the existing runner registry."""

import re
import json
import asyncio

from lfx.custom.custom_component.component import Component
from lfx.io import DropdownInput, Output, StrInput
from lfx.schema import Data
from laomedo.skill_source_client import source_request


class LaomedoSkill(Component):
    display_name = "Laomedo Skill"
    description = "Pass an immutable whole-skill revision to a Laomedo Codex Agent."
    icon = "BookOpen"
    name = "LaomedoSkill"
    inputs = [
        StrInput(name="source", display_name="Source", value="", real_time_refresh=True, track_in_telemetry=False,
                 info="Repository URL or allowed local folder. Leave empty for an existing pinned registry reference."),
        DropdownInput(name="skill_id", display_name="Skill", required=True, options=[],
                      combobox=False, real_time_refresh=True, refresh_button=True,
                      info="Type in the dropdown to filter discovered skills."),
        DropdownInput(name="revision_id", display_name="Revision", required=True, options=[],
                      combobox=False, real_time_refresh=True, refresh_button=True,
                      info="Type in the dropdown to filter discovered revisions."),
        StrInput(name="discovery_status", display_name="Discovery", value="Supply a source to discover skills."),
        StrInput(name="resolved_skill_id", display_name="Resolved Skill ID", value="", show=False),
        StrInput(name="resolved_revision_id", display_name="Resolved Revision", value="", show=False),
        StrInput(name="resolved_selection", display_name="Resolved Selection", value="", show=False),
    ]
    outputs = [Output(name="skill", display_name="Skill Reference", method="skill_output")]

    def skill_output(self) -> Data:
        if getattr(self, "source", ""):
            reference = source_request("resolve", source=str(self.source), skill=str(self.skill_id), revision=str(self.revision_id))
            skill_id, revision = reference["skill_id"], reference["revision_id"]
            if reference.get("tree_hash") != revision:
                raise ValueError("source_reference_invalid")
        else:
            skill_id, revision = str(self.skill_id), str(self.revision_id)
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", skill_id):
            raise ValueError("invalid_skill_id")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", revision):
            raise ValueError("immutable_skill_revision_required")
        self.status = f"{skill_id} at {revision}"
        return Data(data={"skill_id": skill_id, "revision_id": revision, "tree_hash": revision})

    async def update_build_config(self, build_config, field_value, field_name=None):
        for item in self.inputs:
            build_config.setdefault(item.name, item.to_dict())
        changed = field_name in {"source", "skill_id", "revision_id"} and build_config[field_name].get("value") != field_value
        if field_name in {"source", "skill_id", "revision_id"}:
            build_config[field_name]["value"] = field_value
        def clear_resolution():
            for key in ("resolved_skill_id", "resolved_revision_id", "resolved_selection"):
                build_config[key]["value"] = ""
        source = build_config["source"].get("value", "")
        if field_name == "source" and changed:
            for key in ("skill_id", "revision_id"):
                build_config[key].update(value="", options=[])
        elif field_name == "skill_id" and changed:
            build_config["revision_id"].update(value="", options=[])
        clear_resolution()
        if not source:
            return build_config
        for item in self.inputs:
            if item.name in {"skill_id", "revision_id"}:
                definition = item.to_dict()
                for key in ("_input_type", "field_type", "combobox", "refresh_button", "real_time_refresh", "display_name"):
                    if key in definition:
                        build_config[item.name][key] = definition[key]
        skill = build_config["skill_id"].get("value", "")
        revision = build_config["revision_id"].get("value", "")
        try:
            choices = build_config["skill_id"].get("options", [])
            if field_name in {"source", None} or not choices:
                discovered = await asyncio.to_thread(source_request, "discover", source=source)
                choices = [s["choice"] for s in discovered["skills"]]
            build_config["skill_id"]["options"] = choices
            if not skill:
                build_config["discovery_status"]["value"] = f"{len(choices)} skills discovered." if choices else "No skills found in this source."
                return build_config
            if skill not in choices:
                raise ValueError("discovered_skill_required")
            versions = await asyncio.to_thread(source_request, "revisions", source=source, skill=skill)
            options = [v["choice"] for v in versions["revisions"]]
            build_config["revision_id"]["options"] = options
            if revision:
                if revision not in options:
                    raise ValueError("discovered_revision_required")
                ref = await asyncio.to_thread(source_request, "resolve", source=source, skill=skill, revision=revision)
                build_config["resolved_skill_id"]["value"] = ref["skill_id"]
                build_config["resolved_revision_id"]["value"] = ref["revision_id"]
                build_config["resolved_selection"]["value"] = json.dumps([source, skill, revision])
            build_config["discovery_status"]["value"] = f"{len(options)} revisions discovered."
        except ValueError:
            build_config["discovery_status"]["value"] = "Discovery failed. Check source access and refresh."
            for key in ("skill_id", "revision_id"):
                build_config[key].update(value="", options=[])
            clear_resolution()
        return build_config
