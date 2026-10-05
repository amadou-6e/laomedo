"""Host controller for one credential-free, isolated Langflow stage.

The stage container sees only installed Laomedo code, a frozen flow export,
and a tmpfs. It receives no host grant store or account credentials.
"""

from hashlib import sha256
import json
from pathlib import Path
from queue import Empty, Queue
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread
from uuid import uuid4

from laomedo.workflow_run_store import ExternalOutcomeUnknown, LaunchError


IMAGE = "langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0"
PREFIX = "LAOMEDO_STAGE:"


def _digest(value):
    content = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return "sha256:" + sha256(content).hexdigest()


class DockerLangflowStage:
    def __init__(self, exported_flow, *, source_root=None):
        if not isinstance(exported_flow, dict):
            raise LaunchError("unresolved_graph_identity")
        self.export = exported_flow
        self.graph = exported_flow.get("data")
        if not isinstance(self.graph, dict) or not isinstance(self.graph.get("nodes"), list):
            raise LaunchError("unresolved_graph_identity")
        self.code = {}
        for node in self.graph["nodes"]:
            try:
                node_id = node["id"]
                source = node["data"]["node"]["template"]["code"]["value"]
            except (KeyError, TypeError):
                raise LaunchError("unresolved_component_identity") from None
            if (not isinstance(node_id, str) or not node_id or
                    not isinstance(source, str) or not source.strip() or node_id in self.code):
                raise LaunchError("unresolved_component_identity")
            self.code[node_id] = source
        self.source_root = Path(source_root or Path(__file__).resolve().parents[2]).resolve()
        if not (self.source_root / "laomedo" / "work_graph" / "stage_worker.py").is_file():
            raise LaunchError("stage_worker_source_unavailable")

    @classmethod
    def from_saved_flow(cls, flow_id, fetch_export, **kwargs):
        if not isinstance(flow_id, str) or not flow_id or not callable(fetch_export):
            raise LaunchError("saved_flow_identity_unavailable")
        exported = fetch_export(flow_id)
        if not isinstance(exported, dict) or exported.get("id") != flow_id:
            raise LaunchError("saved_flow_identity_mismatch")
        return cls(exported, **kwargs)

    def _command(self, name, flow_dir):
        package = self.source_root / "laomedo"
        return ["docker", "run", "--rm", "-i", "--name", name,
                "--pull=never", "--user", "1000:1000",
                "--network", "none", "--read-only", "--cap-drop", "ALL",
                "--security-opt", "no-new-privileges", "--pids-limit", "128",
                "--memory", "1g", "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
                "--mount", f"type=bind,source={package},target=/repo/laomedo,readonly",
                "--mount", f"type=bind,source={flow_dir},target=/flow,readonly",
                "--workdir", "/repo", "--env", "PYTHONPATH=/repo",
                "--env", "HOME=/tmp", "--entrypoint", "python", IMAGE,
                "-m", "laomedo.work_graph.stage_worker"]

    @staticmethod
    def _ready(process):
        queue = Queue(maxsize=1)

        def reader():
            for line in process.stdout:
                if line.startswith(PREFIX):
                    try:
                        queue.put(json.loads(line[len(PREFIX):]))
                    except ValueError:
                        queue.put(None)
                    return
            queue.put(None)

        Thread(target=reader, daemon=True).start()
        try:
            message = queue.get(timeout=30)
        except Empty:
            raise LaunchError("stage_ready_timeout") from None
        if not isinstance(message, dict) or message.get("type") != "ready":
            raise LaunchError("stage_identity_unavailable")
        return message

    def execute(self, store, *, resolved_config, trigger, inputs=None,
                types=None, outputs=None):
        limits = resolved_config.get("effective_limits") if isinstance(resolved_config, dict) else None
        if not isinstance(limits, dict) or limits.get("max_turns") != 0:
            raise LaunchError("isolated_stage_zero_turn_only")
        timeout = limits.get("timeout_seconds")
        if type(timeout) is not int or not 1 <= timeout <= 3600:
            raise LaunchError("stage_timeout_invalid")
        with TemporaryDirectory(prefix="laomedo-stage-") as directory:
            flow_dir = Path(directory)
            (flow_dir / "flow.json").write_text(json.dumps(self.export), encoding="utf-8")
            name = "laomedo-stage-" + uuid4().hex
            command = self._command(name, flow_dir)
            self.last_command = tuple(command)
            try:
                with subprocess.Popen(command, stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        text=True, encoding="utf-8") as process:
                    try:
                        ready = self._ready(process)
                        expected_codes = {node_id: "sha256:" + sha256(code.encode("utf-8")).hexdigest()
                                          for node_id, code in self.code.items()}
                        if (ready.get("graph_revision") != _digest(self.graph) or
                                ready.get("component_revisions") != expected_codes):
                            raise LaunchError("stage_runtime_identity_mismatch")
                        config = {**resolved_config, "stage_image": IMAGE}
                        record = store.reserve(graph=self.graph, component_code=self.code,
                                               resolved_config=config, trigger=trigger)
                        self.last_run_id = record["run_id"]

                        def dispatch(_run_id):
                            try:
                                process.stdin.write(json.dumps({"type": "execute",
                                    "inputs": inputs, "types": types, "outputs": outputs}) + "\n")
                                process.stdin.flush()
                                output, _ = process.communicate(timeout=timeout)
                            except (subprocess.TimeoutExpired, BrokenPipeError, OSError):
                                raise ExternalOutcomeUnknown("stage_result_unknown") from None
                            messages = []
                            for line in output.splitlines():
                                if line.startswith(PREFIX):
                                    try:
                                        messages.append(json.loads(line[len(PREFIX):]))
                                    except ValueError:
                                        raise ExternalOutcomeUnknown("stage_result_invalid") from None
                            completed = next((message for message in messages
                                              if message.get("type") == "complete"), None)
                            if completed is not None and process.returncode == 0:
                                return completed.get("result")
                            if any(message.get("type") == "failed" for message in messages):
                                raise LaunchError("stage_execution_failed")
                            raise ExternalOutcomeUnknown("stage_result_unknown")

                        result = store.dispatch(record["run_id"], dispatch)
                        return store.get(record["run_id"]), result
                    finally:
                        if process.poll() is None:
                            process.kill()
                            process.wait(timeout=5)
            except OSError as exc:
                raise LaunchError("stage_container_unavailable") from exc
            finally:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True,
                               timeout=10)
