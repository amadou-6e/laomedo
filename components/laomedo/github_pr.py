"""Live repository/label/pr selection and routable graph operations."""
import asyncio
import re
from lfx.custom.custom_component.component import Component
from lfx.io import DataInput, DropdownInput, MultiselectInput, Output, StrInput
from lfx.schema import Data, Message
from laomedo.github_pr_client import pr_request
from laomedo.github_pr_contract import repository_from_url, ERROR_CODES, PRE_DISPATCH_ERRORS


class LaomedoGitHubPR(Component):
    display_name = "GitHub PR"
    description = "Read a live PR or apply a scoped incoming close/modify operation."
    icon = "Github"
    name = "LaomedoGitHubPR"
    inputs = [
        StrInput(name="repository_url", display_name="Repository URL", value="", real_time_refresh=True,
                 info="GitHub repository URL. The connection is configured on the host.", track_in_telemetry=False),
        MultiselectInput(name="labels", display_name="Labels", value=[], options=[],
                         real_time_refresh=True, refresh_button=True, combobox=False,
                         info="Only PRs matching ALL selected labels appear."),
        DropdownInput(name="pr_choice", display_name="PR", value="", options=[], combobox=False,
                      refresh_button=True, real_time_refresh=True),
        DropdownInput(name="state", display_name="State", value="open", options=["open", "closed", "all"],
                      advanced=True, real_time_refresh=True),
        DataInput(name="pr_reference", display_name="PR Reference",
                  info="Connect an earlier GitHub PR output to operate on that same PR. Must match this repository and any explicit selection."),
        DataInput(name="operation", display_name="Operation",
                  info="close or modify(title/body/labels), with request_id and a host-owned grant_ref."),
        StrInput(name="discovery_status", display_name="Discovery", value="Supply a repository URL."),
    ]
    outputs = [
        Output(name="pr", display_name="PR", method="pr_output", group_outputs=True),
        Output(name="task", display_name="Task", method="task_output", group_outputs=True),
        Output(name="operation_result", display_name="Operation Result", method="result_output", group_outputs=True),
    ]

    def _pre_run_setup(self):
        self._pr_execution_cache = None

    def _execution(self):
        cached = getattr(self, "_pr_execution_cache", None)
        if cached is not None:
            return cached
        operation = getattr(self, "operation", None)
        operation = operation.data if isinstance(operation, Data) else operation
        try:
            repository = repository_from_url(self.repository_url)
            selected = str(getattr(self, "pr_choice", "") or "")
            match = re.match(r"^#([1-9][0-9]*) ", selected)
            number = int(match.group(1)) if match else None
            reference = getattr(self, "pr_reference", None)
            reference = reference.data if isinstance(reference, Data) else reference
            if reference:
                if not isinstance(reference, dict) or reference.get("repository") != repository or type(reference.get("number")) is not int:
                    raise ValueError("pr_reference_mismatch")
                if number is not None and number != reference["number"]:
                    raise ValueError("pr_reference_mismatch")
                number = reference["number"]
            if number is None:
                raise ValueError("selected_pr_required")
            result = pr_request("execute", repository_url=self.repository_url, labels=self.labels,
                state=self.state, pr_number=number, operation=operation or None)
        except Exception as error:
            code = str(error) if str(error) in ERROR_CODES else "github_pr_unavailable"
            uncertain = bool(operation) and code not in PRE_DISPATCH_ERRORS
            result = {"schema_version": "laomedo.github-pr.v1", "pr": None,
                      "operation": {"status": "unknown" if uncertain else "failed",
                                    "error_category": "pr_write_unknown" if uncertain else code}}
        self._pr_execution_cache = result
        self.status = result["operation"]["status"]
        return result

    def pr_output(self) -> Data:
        result = self._execution()
        return Data(data=result["pr"] or {"error_category": result["operation"].get("error_category"), "status": result["operation"]["status"]})

    def task_output(self) -> Message:
        result = self._execution()
        pr = result["pr"]
        if not pr or result["operation"]["status"] in {"failed", "unknown"}:
            if getattr(self, "_vertex", None) is not None:
                self.stop("task")
            return Message(text="")
        return Message(text=f"PR: {pr['url']}\nTitle: {pr['title']}\nState: {pr['state']}\nLabels: {', '.join(pr['labels'])}\n\n{pr['body']}")

    def result_output(self) -> Data:
        return Data(data=self._execution())

    async def update_build_config(self, build_config, field_value, field_name=None):
        for item in self.inputs:
            build_config.setdefault(item.name, item.to_dict())
        old = build_config.get(field_name, {}).get("value")
        if field_name in {"repository_url", "labels", "state", "pr_choice"}:
            build_config[field_name]["value"] = field_value
        if old != field_value:
            if field_name == "repository_url":
                build_config["labels"].update(value=[], options=[])
                build_config["pr_choice"].update(value="", options=[])
            elif field_name in {"labels", "state"}:
                build_config["pr_choice"].update(value="", options=[])
        repository = build_config["repository_url"].get("value", "")
        if not repository:
            build_config["discovery_status"]["value"] = "Supply a repository URL."
            return build_config
        try:
            found = await asyncio.to_thread(pr_request, "discover", repository_url=repository,
                labels=build_config["labels"].get("value", []), state=build_config["state"].get("value", "open"))
            build_config["labels"]["options"] = found["labels"]
            choices = [pr["choice"] for pr in found["prs"]]
            build_config["pr_choice"]["options"] = choices
            selected = str(build_config["pr_choice"].get("value") or "")
            identity = re.match(r"^#([1-9][0-9]*) ", selected)
            build_config["pr_choice"]["value"] = next((choice for choice in choices
                if identity and choice.startswith("#" + identity.group(1) + " ")), "")
            build_config["discovery_status"]["value"] = f"{len(choices)} matching PRs." if choices else "No matching PRs."
        except ValueError:
            build_config["pr_choice"].update(value="", options=[])
            build_config["discovery_status"]["value"] = "GitHub discovery failed. Check connection and refresh."
        return build_config
