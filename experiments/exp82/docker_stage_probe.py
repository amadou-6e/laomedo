"""No-model two-phase stage protocol smoke check in the pinned Docker image."""

from copy import deepcopy
import json
from pathlib import Path
from queue import Empty, Queue
import subprocess
from tempfile import TemporaryDirectory
from threading import Thread
from uuid import uuid4


ROOT = Path(__file__).resolve().parents[2]
FLOW = ROOT / "experiments" / "exp03" / "flow.json"
IMAGE = "langflowai/langflow@sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0"
PREFIX = "LAOMEDO_STAGE:"


def no_model_flow():
    flow = deepcopy(json.loads(FLOW.read_text(encoding="utf-8")))
    flow["data"]["nodes"] = [node for node in flow["data"]["nodes"]
                            if node["id"] != "Exp03Pause-exp03"]
    first, second, last = flow["data"]["edges"]
    direct = deepcopy(first)
    direct["id"] = "ChatInput-exp03-Exp03Marker-exp03"
    direct["target"] = "Exp03Marker-exp03"
    direct["data"]["targetHandle"] = second["data"]["targetHandle"]
    direct["targetHandle"] = second["targetHandle"]
    flow["data"]["edges"] = [direct, last]
    return flow


def main():
    with TemporaryDirectory(prefix="laomedo82-stage-") as directory:
        flow_dir = Path(directory)
        (flow_dir / "flow.json").write_text(json.dumps(no_model_flow()), encoding="utf-8")
        name = "laomedo82-stage-" + uuid4().hex
        cmd = ["docker", "run", "--rm", "-i", "--name", name,
               "--network", "none", "--read-only", "--cap-drop", "ALL",
               "--security-opt", "no-new-privileges", "--pids-limit", "128",
               "--memory", "1g", "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
               "--mount", f"type=bind,source={ROOT},target=/repo,readonly",
               "--mount", f"type=bind,source={flow_dir},target=/flow,readonly",
               "--workdir", "/repo", "--env", "PYTHONPATH=/repo",
               "--env", "HOME=/tmp", "--entrypoint", "python", IMAGE,
               "-m", "laomedo.work_graph.stage_worker"]
        process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, text=True, encoding="utf-8")
        try:
            ready_queue = Queue(maxsize=1)

            def read_ready():
                for line in process.stdout:
                    if line.startswith(PREFIX):
                        ready_queue.put(json.loads(line[len(PREFIX):]))
                        return
                ready_queue.put(None)

            Thread(target=read_ready, daemon=True).start()
            try:
                ready = ready_queue.get(timeout=30)
            except Empty:
                raise RuntimeError("stage_ready_timeout") from None
            if not isinstance(ready, dict) or ready.get("type") != "ready":
                raise RuntimeError("stage_not_ready")
            process.stdin.write(json.dumps({"type": "execute",
                "inputs": [{"input_value": "TASK"}], "types": ["chat"],
                "outputs": ["ChatOutput-exp03"]}) + "\n")
            process.stdin.flush()
            output, _ = process.communicate(timeout=30)
            messages = [json.loads(line[len(PREFIX):]) for line in output.splitlines()
                        if line.startswith(PREFIX)]
            completed = next((item for item in messages if item.get("type") == "complete"), None)
            passed = (process.returncode == 0 and completed is not None and
                      "TASK|BEFORE" in completed.get("result", ""))
            report = {"result": "pass" if passed else "fail",
                      "ready": ready.get("type") == "ready",
                      "graph_revision_present": bool(ready.get("graph_revision")),
                      "component_revisions": len(ready.get("component_revisions", {})),
                      "output_marker": bool(completed and "TASK|BEFORE" in completed["result"]),
                      "docker_exit": process.returncode}
            print(json.dumps(report, sort_keys=True))
            if not passed:
                raise RuntimeError("stage_result_failed")
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10)


if __name__ == "__main__":
    main()
