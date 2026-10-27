"""Single-user, zero-turn Work Graph launch from a saved local Langflow flow."""

import json
from pathlib import Path
from threading import Lock
from urllib import error, parse, request

from laomedo.agents.workflow_run_store import LaunchError, WorkflowRunStore

from laomedo.work_graph.grants import LocalGrantAuthority, _private_path
from laomedo.work_graph.launch import launch_github_docker_saved_flow_stage
from laomedo.work_graph.model import GraphSnapshot


class LangflowLocalClient:
    def __init__(self, base_url):
        parsed = parse.urlsplit(base_url)
        if (parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
                or parsed.username or parsed.password or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment):
            raise LaunchError("langflow_loopback_required")
        self.base_url = base_url.rstrip("/")
        self._token_lock = Lock()
        self._token = self._login()

    def _login(self):
        try:
            with request.urlopen(self.base_url + "/api/v1/auto_login", timeout=15) as response:
                token = json.load(response)["access_token"]
        except (OSError, ValueError, KeyError):
            raise LaunchError("langflow_local_login_unavailable") from None
        if not isinstance(token, str) or not token:
            raise LaunchError("langflow_local_login_unavailable")
        return token

    def fetch(self, flow_id):
        if not isinstance(flow_id, str) or not flow_id or "/" in flow_id:
            raise LaunchError("saved_flow_identity_unavailable")
        for attempt in range(2):
            token = self._token
            req = request.Request(self.base_url + "/api/v1/flows/" + parse.quote(flow_id),
                headers={"Authorization": "Bearer " + token, "Accept": "application/json"})
            try:
                with request.urlopen(req, timeout=30) as response:
                    return json.load(response)
            except error.HTTPError as exc:
                exc.close()
                if exc.code == 401 and attempt == 0:
                    # Refresh only the local app login, then repeat this read.
                    # Never repeat a launch or model request on authentication failure.
                    with self._token_lock:
                        if self._token == token:
                            self._token = self._login()
                    continue
                raise LaunchError("saved_flow_fetch_failed") from None
            except (OSError, ValueError):
                raise LaunchError("saved_flow_fetch_failed") from None


def launch_local_saved_flow(*, snapshot_path, work_key, flow_id, langflow_base,
                            grant_store, grant_ref, run_store, task,
                            choice=None, source_root=None):
    frozen = GraphSnapshot.from_dict(json.loads(
        Path(snapshot_path).read_text(encoding="utf-8")))
    authority = LocalGrantAuthority(grant_store)
    run_path = _private_path(run_store)
    if run_path == authority.path:
        raise LaunchError("run_and_grant_store_must_differ")
    store = WorkflowRunStore(run_path)
    client = LangflowLocalClient(langflow_base)
    record, output = launch_github_docker_saved_flow_stage(
        frozen=frozen, work_key=work_key, flow_id=flow_id,
        fetch_export=client.fetch, store=store, grant_ref=grant_ref,
        grant_authority=authority, resolved_config={"mode": "zero-turn-local"},
        choice=choice, inputs=[{"input_value": task}], types=["chat"],
        outputs=None, source_root=source_root)
    return {"run_id": record["run_id"], "trace_id": record["trace_id"],
            "status": record["status"],
            "completion_basis": record["completion_basis"],
            "evidence_complete": bool(record["evidence_complete"]),
            "dispatch_attempts": record["dispatch_attempts"],
            "output_present": bool(output),
            "graph_revision": record["graph_revision"]}
