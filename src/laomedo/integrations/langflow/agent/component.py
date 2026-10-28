"""Provider-neutral graph lifecycle, request identity and runner HTTP boundary."""

import asyncio
import hashlib
import json
import os
from pathlib import Path
import re
import time
from urllib import error; from urllib import request
from urllib.parse import urlsplit
from uuid import UUID; from uuid import uuid4

from laomedo.integrations.langflow.agent.errors import RunnerResultError
from laomedo.agents.runtime.utils import terminal_record as _terminal_record
from lfx.custom.custom_component.component import Component
from lfx.io import DataInput; from lfx.io import DropdownInput; from lfx.io import IntInput; from lfx.io import MessageTextInput; from lfx.io import Output; from lfx.io import StrInput
from lfx.schema import Data; from lfx.schema import Message


_STOP_TASKS = set()
_TERMINAL = {"completed", "cancelled", "failed", "timeout", "interrupted"}
_ROUTABLE_ERRORS = {
    'langflow_loopback_required', 'langflow_local_login_unavailable',
    'saved_flow_identity_unavailable', 'saved_flow_fetch_failed',
    'run_and_grant_store_must_differ',
    'claude_cancelled',
    'claude_container_configuration_invalid',
    'claude_container_image_missing',
    'claude_container_profile_unavailable',
    'claude_container_unavailable',
    'claude_host_login_expired',
    'claude_host_login_unavailable',
    'claude_local_login_copy_failed',
    'claude_mediation_outcome_unknown',
    'claude_model_required',
    'claude_native_skill_policy_unsupported',
    'claude_native_turn_failed',
    'claude_native_turn_limit_mismatch',
    'claude_parent_stop_unverified',
    'claude_process_failed',
    'claude_prompt_too_large',
    'claude_proposal_scope_only',
    'claude_receipt_too_large',
    'claude_session_identity_mismatch',
    'claude_subscription_override_refused',
    'claude_subscription_unavailable',
    'claude_terminal_receipt_invalid',
    'claude_telemetry_start_failed',
    'claude_telemetry_capture_failed',
    'claude_telemetry_cleanup_unconfirmed',
    'claude_turn_timeout',
    'claude_turn_timeout_invalid',
    'claude_workspace_command_invalid',
    'container_termination_unverified',
    'lease_service_required',
    'lease_service_unavailable',
    'resume_auth_identity_mismatch',
    'resume_binding_mismatch',

    "claude_host_login_unavailable", "claude_host_login_expired", "claude_local_login_copy_failed",
    "runner_api_token_file_unavailable", "runner_api_token_file_empty",
    "runner_transport_failed", "runner_invalid_response", "runner_invalid_error_response",
    "runner_response_identity_mismatch", "runner_response_thread_mismatch",
    "runner_request_identity_mismatch", "runner_status_identity_mismatch",
    "runner_wait_deadline", "runner_status_unknown", "turn_timeout",
    "outstanding_command_completion_unknown", "post_run_snapshot_mismatch",
    "experiment_request_binding_denied", "runner_dispatch_refused",
    "standing_policy_inactive", "standing_policy_invalid", "standing_request_denied",
    "standing_issue_context_required", "standing_issue_context_mismatch",
    "standing_pinned_inputs_required", "runner_busy",
    "claude_model_required", "unsupported_claude_effort", "claude_turn_timeout_invalid",
    "claude_native_skill_policy_unsupported", "claude_subscription_unavailable",
    "runner_model_catalog_unavailable_check_runner_connection",
    "pinned_skill_ref_required", "skill_frontmatter_name_required",
}






class _NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, *_):
        return None


_HTTP = request.build_opener(_NoRedirect())


class _ModelCatalog(dict):
    """Model/effort mapping with optional provider presentation metadata."""

    def __init__(self):
        super().__init__()
        self.metadata = {}
        self.effort_aliases = {}


class AgentComponent(Component):
    display_name = "Agent"
    description = "Dispatch work through a provider adapter with optional pinned skills."
    icon = "Bot"
    name = "AgentComponent"

    provider_id = ""
    discover_models_on_upgrade = False
    supports_output_requirements = False
    supports_join_bridge = False
    present_native_models = False
    catalog_timeout_seconds = 30
    catalog_provider = None
    bridge_url_env = ""
    bridge_token_env = ""
    runner_token_env = ""
    runner_token_default = ""

    inputs = [
        MessageTextInput(name="task", display_name="Task"),
        DropdownInput(name="operation", display_name="Operation",
                      options=["fresh", "start", "resume", "status", "cancel"], value="fresh",
                      info="Resume/status/cancel require a reference in an existing serialized flow or API request; node-local run selection is not yet available."),
        StrInput(name="request_id", display_name="Request ID", advanced=True, show=False,
                 info="Optional stable UUID for nonblocking Start retries."),
        DataInput(name="output_requirements", display_name="Output Requirements", show=False,
                  info="Internal expected-answer contract; dedicated Output Contract connections support automatic discovery."),
        StrInput(name="output_requirements_json", display_name="Output Requirements JSON",
                 value="", advanced=True, show=False, info="Internal static pinned requirements when no contract connection is supplied."),
        IntInput(name="output_retries", display_name="Output Continuation Retries", value=1,
                 advanced=True, info="Additional same-session output corrections, separate from infrastructure retries. Safe continuations count in the runner turn ledger."),
        DataInput(name="handoff_reference", display_name="Handoff Provenance", advanced=True),
        StrInput(name="skill_id", display_name="Skill ID", advanced=True, show=False),
        StrInput(name="revision_id", display_name="Skill Revision", advanced=True, show=False),
        DropdownInput(name="model", display_name="Model", value="",
                      options=[], combobox=False, real_time_refresh=True, refresh_button=True,
                      info="Refresh to load models from the configured runner. Runner availability is checked before execution."),
        DropdownInput(name="effort", display_name="Reasoning Effort", value="",
                      options=[], combobox=False),
        DataInput(name="skill_reference", display_name="Skill References", is_list=True,
                  info="Optional pinned skills. Leave disconnected to run the task without skills."),
        DataInput(name="run_reference", display_name="Prior Run", show=False,
                  info="Run Reference from an earlier execution. Used by resume/status/cancel; fresh/start creates a new execution."),
        StrInput(name="run_reference_json", display_name="Prior Run JSON", advanced=True, show=False, override_skip=True,
                 info="For API/manual resume when no Data port is connected."),
        StrInput(name="runner_url", display_name="Runner URL", advanced=True,
                 value="", real_time_refresh=True),
        StrInput(name="bridge_url", display_name="Join Bridge URL", advanced=True, show=False,
                 value="", info="Optional local host bridge for a durable first-call join."),
        IntInput(name="timeout_seconds", display_name="HTTP Timeout", value=210,
                 advanced=True),
    ]
    outputs = [
        Output(name="answer", display_name="Answer", method="answer_output", group_outputs=True),
        Output(name="run", display_name="Run Reference", method="run_output", group_outputs=True),
        Output(name="submission", display_name="Submission / Outcome",
               method="submission_output", group_outputs=True),
    ]

    async def update_build_config(self, build_config, field_value, field_name=None):
        # OpenCode has a separate provider/model and variant contract.
        if not self.discover_models_on_upgrade:
            return build_config
        return await self._update_model_config(build_config, field_value, field_name)

    async def _update_model_config(self, build_config, field_value, field_name=None):
        if field_name == "runner_url":
            if not isinstance(field_value, str):
                raise ValueError("local_runner_url_required")
            build_config["runner_url"]["value"] = field_value
        model_field = build_config.get("model", {})
        effort_field = build_config.get("effort", {})
        if field_name == "model":
            if not isinstance(field_value, str):
                raise ValueError("invalid_model_selection")
            model_field["value"] = field_value
        model = model_field.get("value", "")
        if not isinstance(model, str):
            raise ValueError("invalid_model_selection")
        catalog = await asyncio.to_thread(self._model_catalog, build_config)
        choices = list(catalog)
        if model and model not in choices:
            choices.append(model)  # Preserve imported selections, never substitute.
        model_field.update(options=choices, combobox=False, real_time_refresh=True)
        if self.present_native_models:
            model_field["options_metadata"] = [getattr(catalog, "metadata", {}).get(choice, {}) for choice in choices]
        selected = effort_field.get("value", "")
        if not isinstance(selected, str):
            raise ValueError("invalid_effort_selection")
        efforts = list(catalog.get(model, getattr(catalog, "effort_aliases", {}).get(model, [])))
        if self.present_native_models and efforts == ["default"]:
            effort_field["value"] = "default"
        elif field_name == "model" and selected not in efforts:
            effort_field["value"] = ""
        elif selected and selected not in efforts:
            # Preserve saved values on load; the runner remains authoritative.
            efforts.append(selected)
        effort_field.update(options=efforts, combobox=False)
        return build_config

    def _model_catalog_token_file_path(self):
        return self._runner_token_file_path()

    def _model_catalog(self, build_config):
        base = str(build_config.get("runner_url", {}).get("value") or self.runner_url).rstrip("/")
        parsed = urlsplit(base)
        if (parsed.scheme != "http" or parsed.hostname not in
                {"127.0.0.1", "localhost", "::1", "host.docker.internal"} or
                parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
            raise ValueError("local_runner_url_required")
        # Discovery talks directly to the runner, never with the bridge token.
        try:
            token = Path(self._model_catalog_token_file_path()).read_text(encoding="utf-8").strip()
            if not token:
                raise ValueError("empty_token")
            req = request.Request(base + "/v1/models", headers={"Authorization": "Bearer " + token})
            with _HTTP.open(req, timeout=self.catalog_timeout_seconds) as response:
                raw = response.read(1024 * 1024 + 1)
                if len(raw) > 1024 * 1024:
                    raise ValueError("catalog_too_large")
                payload = json.loads(raw)
            if self.catalog_provider is not None and payload.get('provider') != self.catalog_provider:
                raise ValueError('catalog_provider_mismatch')
            catalog = _ModelCatalog()
            for item in payload["models"]:
                model, efforts = item["id"], item["efforts"]
                if not isinstance(model, str) or not model or model in catalog or not isinstance(efforts, list) or not all(isinstance(x, str) and x for x in efforts):
                    raise ValueError("invalid_catalog")
                catalog[model] = efforts
                if self.present_native_models:
                    catalog.metadata[model] = {"id": model, "laomedo_native_model": True,
                        **({"display_name": item["name"]} if isinstance(item.get("name"), str) else {}),
                        **({"resolved_model": item["resolved_model"]} if isinstance(item.get("resolved_model"), str) else {})}
                    resolved = item.get("resolved_model")
                    if isinstance(resolved, str) and resolved:
                        catalog.effort_aliases.setdefault(resolved, efforts)
                        if model != "default":
                            catalog.metadata[resolved] = {**catalog.metadata[model], "id": resolved}
            if not catalog:
                raise ValueError("empty_catalog")
            return catalog
        except (OSError, ValueError, KeyError, TypeError):
            raise ValueError("runner_model_catalog_unavailable_check_runner_connection") from None

    async def update_frontend_node(self, new_frontend_node, current_frontend_node):
        updated = await super().update_frontend_node(new_frontend_node, current_frontend_node)
        if self.discover_models_on_upgrade:
            try:
                await self.update_build_config(updated["template"], None)
            except ValueError as exc:
                if str(exc) != "runner_model_catalog_unavailable_check_runner_connection":
                    raise
                # Offline component upgrades must not block unrelated fields.
                # Retain saved choices only; explicit refresh still reports failure.
                for name in ("model", "effort"):
                    field = updated["template"].get(name, {})
                    value = field.get("value")
                    field["options"] = [value] if isinstance(value, str) and value else []
                    if self.present_native_models and name == "model":
                        field["options_metadata"] = [{} for _ in field["options"]]
        return updated

    def _pre_run_setup(self):
        # Langflow invokes this once per build. Both output methods share dispatch.
        self._dispatch_task = None
        self._generated_request_id = None
        self._active_run_id = None
        self._stop_request_id = None
        self._stop_request_hash = None
        self._stop_requested = False
        self._cancel_task = None
        self._reference_run_id = None
        self._reference_thread_id = None
        self._prior_trace_ref = None
        self._last_reference = None
        self._contract_submission = None
        self._downstream_contract_binding = None

    def _prepare(self):
        endpoint, payload, method = self._prepare_request()
        connected = getattr(self, "output_requirements", None)
        static = str(getattr(self, "output_requirements_json", "") or "").strip()
        if not static and getattr(self, '_vertex', None) is not None:
            # Langflow omits hidden inputs from component parameters. This
            # internal pin still belongs to the saved graph, including an
            # isolated feedback subgraph; it must not silently lose validation.
            field = self._vertex.full_data.get('data', {}).get('node', {}).get('template', {}).get('output_requirements_json', {})
            static = str(field.get('value') or '').strip()
        if static:
            from laomedo.agents.contracts.output import verify_requirements
            try:
                pinned = verify_requirements(json.loads(static))
            except (TypeError, ValueError):
                raise ValueError("invalid_static_output_requirements") from None
            if connected not in (None, "", []) and verify_requirements(getattr(connected, "data", connected)) != pinned:
                raise ValueError("conflicting_output_requirements")
            connected = pinned
        if self.supports_output_requirements:
            from laomedo.agents.contracts.graph import downstream_requirements
            from laomedo.agents.contracts.output import verify_requirements
            explicit = (verify_requirements(getattr(connected, "data", connected))
                        if connected not in (None, "", []) else None)
            connected = downstream_requirements(self, explicit)
        if connected not in (None, "", []):
            from laomedo.agents.contracts.output import verify_requirements
            if self.operation not in {"fresh", "start"}:
                raise ValueError("output_requirements_require_fresh_start")
            selected = verify_requirements(getattr(connected, "data", connected))
            retries = getattr(self, "output_retries", 1)
            if type(retries) is not int or not 0 <= retries <= 8:
                raise ValueError("invalid_output_retry_count")
            target = payload.get("runner_body", payload)
            target["output_requirements"] = selected
            target["output_retries"] = retries
        provenance = getattr(self, "handoff_reference", None)
        if provenance not in (None, "", []):
            if self.operation not in {"fresh", "start"}:
                raise ValueError("handoff_requires_fresh_operation")
            selected = getattr(provenance, "data", provenance)
            if not isinstance(selected, dict) or set(selected) != {
                    "execution_id", "step", "source", "workspace_policy", "artifact_refs"}:
                raise ValueError("invalid_handoff_reference")
            target = payload.get("runner_body", payload)
            target["handoff"] = {key: selected[key] for key in
                                  ("execution_id", "step", "source", "workspace_policy")}
            target["artifact_refs"] = selected["artifact_refs"]
        return endpoint, payload, method

    def _prepare_request(self):
        base = str(self.runner_url).rstrip("/")
        parsed = urlsplit(base)
        if (parsed.scheme != "http" or parsed.hostname not in
                {"127.0.0.1", "localhost", "::1", "host.docker.internal"} or
                parsed.username or parsed.password or parsed.path or
                parsed.query or parsed.fragment):
            raise ValueError("local_runner_url_required")
        if not 1 <= int(self.timeout_seconds) <= 240:
            raise ValueError("timeout_must_be_1_to_240_seconds")
        operation = str(self.operation)
        if operation not in {"fresh", "start", "resume", "status", "cancel"}:
            raise ValueError("invalid_operation")
        if self._bridge_base() and operation not in {"fresh", "start"}:
            raise ValueError("join_bridge_requires_fresh_start")
        task = str(getattr(self.task, "text", self.task) or "")
        if operation in {"fresh", "start", "resume"} and not task.strip():
            raise ValueError("task_required")
        model, effort = str(self.model), str(self.effort)
        if operation in {"fresh", "start", "resume"} and (not model.strip() or not effort.strip()):
            raise ValueError("model_and_effort_required")
        if operation in {"fresh", "start"}:
            # Imported manual values are not authoritative node settings.
            selected_request_id = (getattr(self, "_generated_request_id", None) or str(uuid4()))
            self._generated_request_id = selected_request_id
            try:
                if str(UUID(selected_request_id)) != selected_request_id:
                    raise ValueError()
            except ValueError:
                raise ValueError("invalid_request_id") from None
            # Blocking fresh is async start followed by read-only polling. A
            # synchronous POST has no identity to reconcile if Stop races its reply.
            endpoint = base + "/v1/runs/async"
            connected = getattr(self, "skill_reference", None)
            refs = [] if connected in (None, "", []) else connected if isinstance(connected, list) else [connected]
            refs = [getattr(ref, "data", ref) for ref in refs]
            if len(refs) > 16:
                raise ValueError("one_to_sixteen_skills_required")
            seen = set()
            for ref in refs:
                if (not isinstance(ref, dict) or
                        not isinstance(ref.get("skill_id"), str) or
                        not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", ref["skill_id"]) or
                        not isinstance(ref.get("revision_id"), str) or
                        not re.fullmatch(r"sha256:[0-9a-f]{64}", ref["revision_id"]) or
                        ref.get("tree_hash") != ref["revision_id"]):
                    raise ValueError("invalid_skill_reference")
                if ref["skill_id"] in seen:
                    raise ValueError("duplicate_skill_id")
                seen.add(ref["skill_id"])
            payload = {"task": task, "model": model, "effort": effort,
                       "request_id": selected_request_id}
            if len(refs) == 1:
                payload["skill_ref"] = {key: refs[0][key] for key in
                                       ("skill_id", "revision_id", "tree_hash")}
            else:
                payload["skill_refs"] = refs
            return self._fresh_route(endpoint, payload, selected_request_id)
        prior = getattr(self.run_reference, "data", self.run_reference)
        if prior in (None, "", []) and getattr(self, "run_reference_json", None):
            try:
                prior = json.loads(self.run_reference_json)
            except (ValueError, TypeError):
                raise ValueError("invalid_prior_run_json") from None
        if not isinstance(prior, dict):
            raise ValueError("prior_run_required")
        run_id = str(prior.get("run_id", ""))
        try:
            if str(UUID(run_id)) != run_id:
                raise ValueError()
        except ValueError:
            raise ValueError("invalid_run_id") from None
        endpoint = base + "/v1/runs/" + run_id
        self._reference_run_id = run_id
        self._prior_trace_ref = prior.get("trace_ref")
        if operation == "status":
            return endpoint, None, "GET"
        if operation == "cancel":
            return endpoint + "/cancel", {}, "POST"
        snapshot, thread = prior.get("post_run_hash"), prior.get("thread_id")
        if (prior.get("status") != "completed" or not isinstance(snapshot, str) or
                not re.fullmatch(r"sha256:[0-9a-f]{64}", snapshot) or
                not isinstance(thread, str) or not thread.strip()):
            raise ValueError("completed_snapshot_and_thread_required")
        if prior.get("model") != model or prior.get("effort") != effort:
            raise ValueError("resume_model_effort_mismatch")
        self._reference_thread_id = thread
        return endpoint + "/resume", {"task": task, "model": model, "effort": effort,
            "expected_post_run_hash": snapshot, "expected_thread_id": thread}, "POST"

    def _bridge_base(self):
        # Provider configuration must not redirect unrelated lifecycle
        # operations. Stop handling during a fresh/start invocation still uses
        # the bridge so its in-flight request can be reconciled correctly.
        if not self.supports_join_bridge or str(self.operation) not in {"fresh", "start"}:
            return ""
        base = str(os.environ.get(self.bridge_url_env, getattr(self, "bridge_url", "")) or "").rstrip("/")
        if not base:
            return ""
        parsed = urlsplit(base)
        if (parsed.scheme != "http" or parsed.hostname not in
                {"127.0.0.1", "localhost", "::1", "host.docker.internal"} or
                parsed.username or parsed.password or parsed.path or
                parsed.query or parsed.fragment):
            raise ValueError("local_bridge_url_required")
        return base

    def _fresh_route(self, endpoint, payload, client_request_id):
        bridge = self._bridge_base()
        if not bridge:
            return endpoint, payload, "POST"
        graph = getattr(self, "graph", None)
        vertex = getattr(self, "_vertex", None)
        flow_id = getattr(graph, "flow_id", None)
        graph_run_id = getattr(graph, "run_id", None)
        stage_id = getattr(vertex, "id", None)
        if (not isinstance(flow_id, str) or not flow_id or
                not isinstance(graph_run_id, str) or not graph_run_id or
                not isinstance(stage_id, str) or not stage_id):
            raise ValueError("join_bridge_execution_identity_unavailable")
        return bridge + "/v1/invocations", {
            "client_request_id": client_request_id,
            "flow_id": flow_id, "graph_run_id": graph_run_id,
            "stage_id": stage_id,
            "runner_body": {key: value for key, value in payload.items()
                            if key != "request_id"}}, "POST"

    def _token_file_path(self):
        if self._bridge_base():
            return os.environ.get(self.bridge_token_env,
                                  "/run/secrets/laomedo-bridge-token")
        return self._runner_token_file_path()

    def _runner_token_file_path(self):
        """Activity always polls the runner, even when dispatch uses a bridge."""
        return os.environ.get(self.runner_token_env, self.runner_token_default)

    def _token(self):
        try:
            token = Path(self._token_file_path()).read_text(encoding="utf-8").strip()
        except OSError:
            raise RuntimeError("runner_api_token_file_unavailable") from None
        if not token:
            raise RuntimeError("runner_api_token_file_empty")
        return token

    def _stop_http(self, endpoint, payload, method, token):
        req = request.Request(endpoint,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + token}, method=method)
        try:
            opener = _HTTP.open if self._bridge_base() else request.urlopen
            with opener(req, timeout=10) as response:
                value = json.load(response)
        except error.HTTPError as exc:
            if method == "GET" and exc.code == 404:
                return None
            raise RuntimeError("stop_runner_http_error") from None
        except (error.URLError, TimeoutError, OSError, ValueError, TypeError):
            raise RuntimeError("stop_runner_transport_unknown") from None
        if not isinstance(value, dict):
            raise RuntimeError("stop_runner_invalid_response")
        return value

    def _cancel_after_ui_stop(self, base, request_id, expected_hash):
        """Resolve a stopped invocation without a second POST or guessed run ID."""
        try:
            token = self._token()
            deadline = time.monotonic() + min(240, max(10, int(self.timeout_seconds)))
            run_id = None
            status = None
            while time.monotonic() < deadline:
                candidate = self._stop_http(base + "/v1/requests/" + request_id,
                                            None, "GET", token)
                if candidate is None:
                    time.sleep(.2)
                    continue
                if (candidate.get("client_request_id") != request_id or
                        candidate.get("request_hash") != expected_hash):
                    raise RuntimeError("stop_request_binding_conflict")
                run_id, status = candidate.get("run_id"), candidate.get("status")
                if not isinstance(run_id, str) or str(UUID(run_id)) != run_id:
                    raise RuntimeError("stop_runner_identity_unknown")
                if self._active_run_id and self._active_run_id != run_id:
                    raise RuntimeError("stop_runner_identity_conflict")
                break
            if run_id is None:
                raise RuntimeError("stop_runner_identity_unknown")
            self._active_run_id = run_id
            if _terminal_record(candidate):
                self.status = f"Laomedo run {run_id}: already {status}; no cancel sent"
                return
            if status not in {"prepared", "running"}:
                raise RuntimeError("stop_runner_status_unknown")
            self._stop_http(base + "/v1/runs/" + run_id + "/cancel", {}, "POST", token)
            self.status = f"Laomedo run {run_id}: cancel requested; outcome unknown"
            while time.monotonic() < deadline:
                current = self._stop_http(base + "/v1/runs/" + run_id,
                                          None, "GET", token)
                if current is None or current.get("run_id") != run_id:
                    raise RuntimeError("stop_runner_status_unknown")
                if _terminal_record(current):
                    confirmed = (current.get("status") == "cancelled" and
                                 current.get("cancel_confirmed") is True)
                    self.status = (f"Laomedo run {run_id}: cancellation confirmed" if confirmed
                                   else f"Laomedo run {run_id}: {current.get('status')}; "
                                        "cancellation unconfirmed")
                    return
                time.sleep(.2)
            raise RuntimeError("stop_runner_result_pending")
        except (RuntimeError, ValueError) as exc:
            self.status = f"Laomedo Stop: {exc}; remote outcome unknown"

    def _cancel_after_ui_stop_bridge(self, base, client_request_id):
        """Persist Stop by client UUID even before the first bridge reply."""
        try:
            token = self._token()
            self._stop_http(base + "/v1/requests/" + client_request_id + "/cancel",
                            {}, "POST", token)
            deadline = time.monotonic() + min(240, max(10, int(self.timeout_seconds)))
            while time.monotonic() < deadline:
                current = self._stop_http(base + "/v1/requests/" + client_request_id,
                                          None, "GET", token)
                if current is None:
                    time.sleep(.2)
                    continue
                if current.get("client_request_id") != client_request_id:
                    raise RuntimeError("stop_request_binding_conflict")
                status = current.get("status")
                if status == "cancelled" and current.get("cancel_confirmed") is True:
                    self.status = "Laomedo Stop: native cancellation confirmed"
                    return
                if status == "cancelled" and current.get("run_id") is None:
                    self.status = "Laomedo Stop: cancelled before runner dispatch"
                    return
                if _terminal_record(current):
                    self.status = f"Laomedo Stop: runner {status}; cancellation unconfirmed"
                    return
                time.sleep(.2)
            raise RuntimeError("stop_runner_result_pending")
        except (RuntimeError, ValueError) as exc:
            self.status = f"Laomedo Stop: {exc}; remote outcome unknown"

    def _http(self, endpoint, payload, method):
        token = self._token()
        req = request.Request(endpoint,
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Content-Type": "application/json",
                     "Authorization": "Bearer " + token}, method=method)
        try:
            opener = _HTTP.open if self._bridge_base() else request.urlopen
            with opener(req, timeout=int(self.timeout_seconds)) as response:
                result = json.load(response)
        except error.HTTPError as exc:
            try:
                result = json.load(exc)
            except (ValueError, TypeError):
                raise RuntimeError("runner_invalid_error_response") from None
            if not isinstance(result, dict):
                raise RuntimeError("runner_invalid_error_response")
            if self._reference_run_id and result.get("run_id") not in (None, self._reference_run_id):
                raise RuntimeError("runner_response_identity_mismatch") from None
            if not (self.operation == "cancel" and result.get("run_id") and
                    result.get("status") in {"completed", "cancelled", "failed", "timeout"}):
                if result.get("run_id") or self._reference_run_id:
                    if not result.get("run_id"):
                        # This is a request refusal, not a failed new turn on
                        # the previously completed run.
                        result["run_id"] = self._reference_run_id
                        result["status"] = "unknown"
                    result.setdefault("status", "unknown")
                    result.setdefault("raw_event_ref", self._prior_trace_ref)
                    raise RunnerResultError(self._run_reference(result)) from None
                # A complete pre-dispatch refusal has no run identity. Expose
                # only a fixed public code, never arbitrary server error text.
                category = result.get("error_category")
                code = (category if isinstance(category, str) and category in
                        _ROUTABLE_ERRORS else "runner_dispatch_refused")
                if 400 <= exc.code < 500:
                    raise RuntimeError(code) from None
                raise RuntimeError("runner_runtime_unknown") from None
        except (error.URLError, TimeoutError, OSError):
            if self._reference_run_id:
                reference = self._run_reference({"run_id": self._reference_run_id,
                    "status": "unknown", "raw_event_ref": self._prior_trace_ref,
                    "error_category": "runner_transport_failed"})
                raise RunnerResultError(reference,
                    f"runner_transport_failed; Laomedo run {self._reference_run_id}; "
                    "remote execution may still be active") from None
            if self.operation == "start":
                raise RuntimeError("runner_transport_failed; start outcome unknown; "
                                   "check status for request_id before starting again: " +
                                   str(payload.get("request_id"))) from None
            raise RuntimeError("runner_transport_failed; remote execution may still be active") from None
        except (ValueError, TypeError):
            raise RuntimeError("runner_invalid_response") from None
        if not isinstance(result, dict) or not result.get("run_id"):
            raise RuntimeError("runner_invalid_response")
        if self._reference_run_id and result["run_id"] != self._reference_run_id:
            raise RuntimeError("runner_response_identity_mismatch")
        if (self.operation == "resume" and result.get("status") == "completed" and
                result.get("thread_id") != self._reference_thread_id):
            raise RuntimeError("runner_response_thread_mismatch")
        if self.operation in {"fresh", "start"}:
            if result.get("client_request_id") != self._stop_request_id:
                raise RuntimeError("runner_request_identity_mismatch")
            self._active_run_id = result["run_id"]
            capture = getattr(self, "_activity_capture", None)
            if capture is not None:
                capture.bind(result["run_id"],result.get('activity_initial_attempt_id'))
        self._last_reference = self._run_reference(result)
        if self.operation == "fresh":
            deadline = time.monotonic() + int(self.timeout_seconds)
            read_failures = 0
            while not _terminal_record(result) and not self._stop_requested:
                if time.monotonic() >= deadline:
                    raise RuntimeError("runner_wait_deadline; remote execution may still be active")
                time.sleep(.2)
                try:
                    opener = _HTTP.open if self._bridge_base() else request.urlopen
                    with opener(request.Request(
                            (self._bridge_base() or str(self.runner_url).rstrip("/")) +
                            "/v1/runs/" + result["run_id"],
                            headers={"Authorization": "Bearer " + token}, method="GET"),
                            timeout=min(10, max(.1, deadline - time.monotonic()))) as response:
                        result = json.load(response)
                except error.HTTPError:
                    raise RuntimeError("runner_status_unknown; remote execution may still be active") from None
                except (error.URLError, TimeoutError, OSError):
                    # Retry only reads of the already-bound run. Never repeat
                    # dispatch or another effect after a transport interruption.
                    read_failures += 1
                    if read_failures >= 3 or time.monotonic() >= deadline:
                        raise RuntimeError("runner_status_unknown; remote execution may still be active") from None
                    continue
                except (ValueError, TypeError):
                    raise RuntimeError("runner_status_unknown; remote execution may still be active") from None
                if not isinstance(result, dict) or result.get("run_id") != self._active_run_id:
                    raise RuntimeError("runner_status_identity_mismatch")
                read_failures = 0
                self._last_reference = self._run_reference(result)
        if (self.operation in {"fresh", "resume"} and not self._stop_requested and
                result.get("status") != "completed"):
            raise RunnerResultError(self._run_reference(result))
        return self._run_reference(result)

    def _run_reference(self, result):
        skill = result.get("skill") or {}
        skills = result.get("skills") or ([skill] if skill else [])
        return {"answer": result.get("answer"), "run_id": result["run_id"],
            "request_id": result.get("client_request_id"),
            "invocation_id": result.get("invocation_id"),
            "laomedo_run_id": result.get("laomedo_run_id"),
            "trace_id": result.get("trace_id"),
            "evidence_complete": (result.get("evidence_complete") if
                                  type(result.get("evidence_complete")) is bool else "unknown"),
            "completion_basis": result.get("completion_basis"),
            "requirements_revision": result.get("requirements_revision"),
            "precheck": {key: (result.get("precheck", {}).get(key) if
                         isinstance(result.get("precheck"), dict) and
                         (type(result["precheck"].get(key)) is bool if key != "call_count"
                          else type(result["precheck"].get(key)) is int and
                          result["precheck"][key] >= 0) else "unknown")
                         for key in ("installed", "call_count")},
            "provider": result.get("provider") or self.provider_id,
            "handoff": result.get("handoff"), "imported_artifacts": result.get("imported_artifacts", []),
            "thread_id": result.get("thread_id"), "status": result.get("status"),
            "post_run_hash": result.get("post_run_hash"),
            "model": result.get("requested_model"), "effort": result.get("requested_effort"),
            "skill_revision": skill.get("revision_id"),
            "skill_use_evidence": skill.get("use_evidence", "unknown"),
            "skills": skills,
            "artifact_ref": result.get("output_ref"), "trace_ref": result.get("raw_event_ref"),
            "error_category": result.get("error_category"),
            "attempt_finished": result.get("attempt_finished", False),
            "snapshot_ready": result.get("snapshot_ready", False),
            "cancel_requested": result.get("cancel_requested", False),
            "usage": result.get("usage") if isinstance(result.get("usage"), dict) else "unknown"}

    async def _result(self):
        if getattr(self, "_dispatch_task", None) is None:
            prepared = self._prepare()
            if self.operation in {"fresh", "start"}:
                payload = prepared[1]
                if self._bridge_base():
                    self._stop_request_id = payload["client_request_id"]
                    canonical = payload["runner_body"]
                else:
                    self._stop_request_id = payload["request_id"]
                    canonical = {key: value for key, value in payload.items()
                                 if key != "request_id"}
                self._stop_request_hash = "sha256:" + hashlib.sha256(
                    json.dumps(canonical, sort_keys=True, separators=(",", ":"),
                               ensure_ascii=False).encode("utf-8")).hexdigest()
            from laomedo.activity.agent_activity.utils import dispatch_with_capture
            self._dispatch_task = asyncio.create_task(asyncio.to_thread(dispatch_with_capture, self, prepared))
        try:
            # Shield the HTTP call so the same request identity can be reconciled.
            result = await asyncio.shield(self._dispatch_task)
        except asyncio.CancelledError:
            self._stop_requested = True
            if self._stop_request_id and self._cancel_task is None:
                bridge = self._bridge_base()
                if bridge:
                    self._cancel_task = asyncio.create_task(asyncio.to_thread(
                        self._cancel_after_ui_stop_bridge, bridge,
                        self._stop_request_id))
                else:
                    base = str(self.runner_url).rstrip("/")
                    self._cancel_task = asyncio.create_task(asyncio.to_thread(
                        self._cancel_after_ui_stop, base, self._stop_request_id,
                        self._stop_request_hash))
                _STOP_TASKS.add(self._cancel_task)
                self._cancel_task.add_done_callback(_STOP_TASKS.discard)
            self.status = "Laomedo Stop requested; remote outcome unknown"
            raise
        self.status = f"Laomedo run {result['run_id']}: {result['status']}"
        return result

    async def run_output(self) -> Data:
        return Data(data=await self._result())

    async def answer_output(self) -> Message:
        result = await self._result()
        return Message(text=result.get("answer") or "")

    async def submission_output(self) -> Data:
        """Route known runtime failures; legacy outputs retain their exceptions."""
        try:
            reference = await self._result()
        except RunnerResultError as exc:
            reference = dict(exc.run_reference)
            if (self.operation in {"fresh", "start"} and
                    reference.get("request_id") != self._stop_request_id):
                # Legacy exceptions can contain an unbound HTTP error record.
                # A graph output must not adopt its unsolicited run/trace identity.
                reference = dict(self._last_reference or {})
                reference.update(status="unknown", evidence_complete=False,
                    artifact_ref=None, error_category="runner_request_identity_mismatch")
                reference.setdefault("run_id", self._active_run_id)
                reference.setdefault("request_id", self._stop_request_id)
        except RuntimeError as exc:
            # Input ValueErrors and framework cancellation still refuse/abort.
            # Never put raw exception text, HTTP bodies or exception paths in Data.
            code = str(exc).split(";", 1)[0]
            if code not in _ROUTABLE_ERRORS:
                code = "runner_runtime_unknown"
            reference = dict(self._last_reference or {})
            reference.update(status="unknown", evidence_complete=False,
                             artifact_ref=None, error_category=code)
            reference.setdefault("run_id", self._reference_run_id)
            reference.setdefault("trace_ref", self._prior_trace_ref)
            reference.setdefault("request_id", self._stop_request_id)
        category = reference.get("error_category")
        if category is not None and (not isinstance(category, str) or category not in _ROUTABLE_ERRORS):
            reference = {**reference, "error_category": "runner_runtime_unknown"}
        answer = reference.get("answer")
        submission = None
        if isinstance(answer, str):
            try:
                parsed = json.loads(answer)
            except (ValueError, TypeError):
                parsed = None
            if isinstance(parsed, dict):
                submission = parsed
        reported = (submission or {}).get("task_outcome")
        outcome = (reported if isinstance(reported, str) and
                   reported in {"success", "failure"} else "unknown")
        # Even an explicit claim of success cannot promote an incomplete executor.
        if outcome == "success" and reference.get("status") != "completed":
            outcome = "unknown"
        value = {"schema_version": "laomedo.agent-submission.v1",
                 "submission": submission, "answer": answer,
                 "requirements_revision": reference.get("requirements_revision"),
                 "precheck": reference.get("precheck", {"installed": "unknown",
                                                       "call_count": "unknown"}),
                 "task_outcome": outcome,
                 "executor_status": reference.get("status") or "unknown",
                 "evidence_complete": reference.get("evidence_complete", "unknown"),
                 "run_reference": reference,
                 "error_category": reference.get("error_category")}
        from copy import deepcopy
        self._contract_submission = deepcopy(value)
        self.status = "Laomedo outcome: " + value["executor_status"]
        return Data(data=value)
