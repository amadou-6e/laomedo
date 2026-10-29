"""Implementation owned by work_graph / docker_stage."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from queue import Empty
from queue import Queue
from tempfile import TemporaryDirectory
from threading import Thread
from time import monotonic
from uuid import uuid4
import json
import laomedo._paths as _package_paths
import laomedo.work_graph.runs.errors as _workflow_errors
import laomedo.work_graph.settings as _work_graph_settings
import laomedo.work_graph.serialization as _work_graph_serialization
import subprocess


class DockerLangflowStage:
    def __init__(self, exported_flow, *, source_root=None):
        if not isinstance(exported_flow, dict):
            raise _workflow_errors.LaunchError("unresolved_graph_identity")
        self.export = deepcopy(exported_flow)
        self.graph = self.export.get("data")
        if not isinstance(self.graph, dict) or not isinstance(
            self.graph.get("nodes"), list
        ):
            raise _workflow_errors.LaunchError("unresolved_graph_identity")
        self.code = {}
        for node in self.graph["nodes"]:
            try:
                node_id = node["id"]
                source = node["data"]["node"]["template"]["code"]["value"]
            except (KeyError, TypeError):
                raise _workflow_errors.LaunchError(
                    "unresolved_component_identity"
                ) from None
            if (
                not isinstance(node_id, str)
                or not node_id
                or not isinstance(source, str)
                or not source.strip()
                or node_id in self.code
            ):
                raise _workflow_errors.LaunchError("unresolved_component_identity")
            self.code[node_id] = source
        self.graph_revision = _work_graph_serialization._digest(self.graph)
        self.component_revisions = {
            node_id: "sha256:" + sha256(code.encode("utf-8")).hexdigest()
            for node_id, code in self.code.items()
        }
        self.flow_bytes = json.dumps(
            self.export, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        self.flow_digest = "sha256:" + sha256(self.flow_bytes).hexdigest()
        self.source_root = Path(source_root or _package_paths.import_root()).resolve()
        # Existing host configurations pass the checkout root. Accept that fixed
        # src-layout location as well as an installed/importable package root.
        if not (
            self.source_root / "laomedo" / "work_graph" / "stage_worker.py"
        ).is_file():
            source_layout = self.source_root / "src"
            if (source_layout / "laomedo" / "work_graph" / "stage_worker.py").is_file():
                self.source_root = source_layout
        if not (
            self.source_root / "laomedo" / "work_graph" / "stage_worker.py"
        ).is_file():
            raise _workflow_errors.LaunchError("stage_worker_source_unavailable")

    @classmethod
    def from_saved_flow(cls, flow_id, fetch_export, **kwargs):
        if not isinstance(flow_id, str) or not flow_id or not callable(fetch_export):
            raise _workflow_errors.LaunchError("saved_flow_identity_unavailable")
        exported = fetch_export(flow_id)
        if not isinstance(exported, dict) or exported.get("id") != flow_id:
            raise _workflow_errors.LaunchError("saved_flow_identity_mismatch")
        return cls(exported, **kwargs)

    def _command(self, name, flow_dir, mode):
        package = self.source_root / "laomedo"
        return [
            "docker",
            "run",
            "--rm",
            "-i",
            "--name",
            name,
            "--pull=never",
            "--user",
            "1000:1000",
            "--network",
            "none",
            "--read-only",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges",
            "--pids-limit",
            "128",
            "--memory",
            "1g",
            "--tmpfs",
            "/tmp:rw,nosuid,nodev,size=64m",
            "--mount",
            f"type=bind,source={package},target=/repo/laomedo,readonly",
            "--mount",
            f"type=bind,source={flow_dir},target=/flow,readonly",
            "--workdir",
            "/repo",
            "--env",
            "PYTHONPATH=/repo",
            "--env",
            "HOME=/tmp",
            "--entrypoint",
            "python",
            _work_graph_settings.IMAGE,
            "-m",
            "laomedo.work_graph.stage_worker",
            mode,
        ]

    def _validate(self, flow_dir):
        name = "laomedo-stage-check-" + uuid4().hex
        command = self._command(name, flow_dir, "validate")
        self.last_validation_command = tuple(command)
        try:
            result = subprocess.run(
                command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=30,
            )
            if result.returncode != 0:
                raise _workflow_errors.LaunchError("stage_validation_failed")
        except subprocess.TimeoutExpired:
            raise _workflow_errors.LaunchError("stage_validation_timeout") from None
        except OSError as exc:
            raise _workflow_errors.LaunchError("stage_container_unavailable") from exc
        finally:
            subprocess.run(
                ["docker", "rm", "-f", name], capture_output=True, timeout=10
            )

    @staticmethod
    def _untrusted_result(process, payload, timeout):
        """Bound stdout as data; only Docker's exit status controls outcome."""
        queue = Queue(maxsize=1)

        def reader():
            parts, size = [], 0
            try:
                while chunk := process.stdout.read(4096):
                    size += len(chunk)
                    if size > _work_graph_settings.MAX_RESULT_CHARS:
                        queue.put((False, "stage_output_limit"))
                        return
                    parts.append(chunk)
                queue.put((True, "".join(parts)))
            except (OSError, UnicodeError):
                queue.put((False, "stage_output_unreadable"))

        Thread(target=reader, daemon=True).start()
        started = monotonic()
        try:
            process.stdin.write(payload + "\n")
            process.stdin.flush()
            process.stdin.close()
            valid, output = queue.get(timeout=timeout)
            if not valid:
                raise _workflow_errors.ExternalOutcomeUnknown(output)
            process.wait(timeout=max(0.001, timeout - (monotonic() - started)))
        except (Empty, subprocess.TimeoutExpired, BrokenPipeError, OSError):
            raise _workflow_errors.ExternalOutcomeUnknown(
                "stage_result_unknown"
            ) from None
        if process.returncode != 0:
            raise _workflow_errors.LaunchError("stage_execution_failed")
        return output.strip()

    def execute(
        self, store, *, resolved_config, trigger, inputs=None, types=None, outputs=None
    ):
        limits = (
            resolved_config.get("effective_limits")
            if isinstance(resolved_config, dict)
            else None
        )
        if not isinstance(limits, dict) or limits.get("max_turns") != 0:
            raise _workflow_errors.LaunchError("isolated_stage_zero_turn_only")
        timeout = limits.get("timeout_seconds")
        if type(timeout) is not int or not 1 <= timeout <= 3600:
            raise _workflow_errors.LaunchError("stage_timeout_invalid")
        with TemporaryDirectory(prefix="laomedo-stage-") as directory:
            flow_dir = Path(directory)
            (flow_dir / "flow.json").write_bytes(self.flow_bytes)
            if (
                "sha256:" + sha256((flow_dir / "flow.json").read_bytes()).hexdigest()
                != self.flow_digest
            ):
                raise _workflow_errors.LaunchError("stage_input_identity_mismatch")
            self._validate(flow_dir)
            config = {
                **resolved_config,
                "stage_image": _work_graph_settings.IMAGE,
                "stage_input_digest": self.flow_digest,
                "stage_control": "host-owned-v2",
            }
            record = store.reserve(
                graph=self.graph,
                component_code=self.code,
                resolved_config=config,
                trigger=trigger,
            )
            self.last_run_id = record["run_id"]
            if (
                record["graph_revision"] != self.graph_revision
                or record["component_revisions"] != self.component_revisions
            ):
                raise _workflow_errors.LaunchError("recorded_stage_identity_mismatch")

            name = "laomedo-stage-" + uuid4().hex
            command = self._command(name, flow_dir, "execute")
            self.last_command = tuple(command)

            def dispatch(_run_id):
                try:
                    with subprocess.Popen(
                        command,
                        stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL,
                        text=True,
                        encoding="utf-8",
                    ) as process:
                        try:
                            return self._untrusted_result(
                                process,
                                json.dumps(
                                    {
                                        "type": "execute",
                                        "inputs": inputs,
                                        "types": types,
                                        "outputs": outputs,
                                    }
                                ),
                                timeout,
                            )
                        finally:
                            if process.poll() is None:
                                process.kill()
                                process.wait(timeout=5)
                except OSError as exc:
                    raise _workflow_errors.ExternalOutcomeUnknown(
                        "stage_container_unavailable"
                    ) from exc
                finally:
                    subprocess.run(
                        ["docker", "rm", "-f", name], capture_output=True, timeout=10
                    )

            result = store.dispatch(
                record["run_id"], dispatch, completion_basis="process_exit"
            )
            return store.get(record["run_id"]), result
