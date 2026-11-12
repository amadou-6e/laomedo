"""Real maintained Codex graph acceptance; aggregate evidence only."""
import asyncio
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
import tempfile
import threading
import time
from uuid import uuid4

REPO = Path("C:/CodeWorkspace/laomedo")
sys.path.insert(0, str(REPO / "src"))

def main():
    with tempfile.TemporaryDirectory(prefix="laomedo-owner-graph-") as directory:
        root = Path(directory)
        os.environ.update(PYTHONPATH=str(REPO / "src"), LAOMEDO_AGENT_ACTIVITY_DB=str(root / "activity.db"), LANGFLOW_CONFIG_DIR=str(root / "langflow"), LFX_CONFIG_DIR=str(root / "langflow"), LANGFLOW_DO_NOT_TRACK="true")
        from laomedo.agents.agents.codex.agent import CodexAgent
        from laomedo.host.runner.http.server import RunnerServer
        from laomedo.agents.activity.store import ActivityStore
        native = runpy.run_path(str(REPO / ".tools/worktrees/docker-acceptance-exp/experiments/docker-boundary-277/acceptance.py"))
        source = root / "repository/source"
        source.mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet", str(source.parent)], check=True)
        (source / "task.txt").write_text("Acceptance marker: amber-205.\n", encoding="utf-8")
        lease = root / "lease"
        with (root / "supervisor.log").open("wb") as log:
            supervisor = subprocess.Popen([sys.executable, "-m", "laomedo.host.leases.service_cli", "serve", "--state", str(lease)], stdout=log, stderr=log, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            server = None
            try:
                deadline = time.monotonic() + 30
                while not (lease / "service.json").exists():
                    if supervisor.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError("lease_start_failed")
                    time.sleep(.1)
                agent = CodexAgent(root / "runner", root / "registry", source, lease_service=lease, **native["session_login"]())
                server = RunnerServer(agent, port=0)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                token = root / "runner-token"
                token.write_text(agent.api_token, encoding="utf-8")
                os.environ["LAOMEDO_RUNNER_TOKEN_FILE"] = str(token)
                catalog = agent.catalog.list_models()
                model = next((m for m in catalog.models if m.id == "gpt-6-luna"), catalog.models[0])
                efforts = model.reasoning_efforts
                effort = "low" if "low" in efforts else (efforts[0] if efforts else "default")
                builder = runpy.run_path(str(REPO / "examples/agents/build_flow.py"))["build"]
                flow = builder(provider="codex", model=model.id, effort=effort, runner_url="http://127.0.0.1:" + str(server.server_port), task="Read task.txt and reply only with its marker. Do not edit files or delegate.", workflow="resume", follow_up="What marker did you just read? Reply only with that marker, without tools or delegation.")
                from lfx.graph.graph.base import Graph
                flow_id, owner = str(uuid4()), str(uuid4())
                graph = Graph.from_payload(flow, flow_id=flow_id, user_id=owner)
                print(json.dumps({"stage":"graph_start", "revision":subprocess.check_output(["git","rev-parse","HEAD"],cwd=REPO,text=True).strip(), "nodes":len(flow["data"]["nodes"]),"edges":len(flow["data"]["edges"]),"model":model.id}), flush=True)
                asyncio.run(graph.arun(inputs=[{}], outputs=["follow-up"]))
                records = [json.loads(p.read_text()) for p in (agent.state / "runs").glob("*/record.json")]
                print(json.dumps({"stage":"run_summary","run_count":len(records),"statuses":[r.get("status") for r in records],"marker_in_record":["amber-205" in (r.get("answer") or "") for r in records]}),flush=True)
                assert len(records) == 1, "resume_created_second_run"
                record = records[0]
                assert record["status"] == "completed", "graph_not_completed"
                assert "amber-205" in (record.get("answer") or ""), "marker_missing"
                store = ActivityStore(root / "activity.db", read_only=True)
                deadline = time.monotonic() + 30
                while True:
                    with store.db() as db:
                        pending = db.execute("SELECT COUNT(*) FROM agent_activity_runs WHERE stream_state != 'complete'").fetchone()[0]
                    if not pending or time.monotonic() > deadline:
                        break
                    time.sleep(.2)
                with store.db() as db:
                    runs = [dict(r) for r in db.execute("SELECT node,status,stream_state,id,runner_run_id FROM agent_activity_runs ORDER BY started")]
                    receipts = db.execute("SELECT COUNT(*) FROM agent_activity_receipts").fetchone()[0]
                print(json.dumps({"stage":"capture_summary", "runs":[{k:v for k,v in r.items() if k in ("node","status","stream_state")} for r in runs],"receipts":receipts}),flush=True)
                assert len(runs) == 2 and {r["node"] for r in runs} == {"agent","follow-up"}, "capture_identity_missing"
                assert all(r["status"] == "completed" and r["stream_state"] == "complete" for r in runs), "capture_incomplete"
                assert receipts > 0, "activity_empty"
                print(json.dumps({"stage":"graph_complete", "status":record["status"], "same_run":len(records)==1,"marker_ok":True,"activity_invocations":len(runs),"activity_receipts":receipts,"all_streams_complete":True}),flush=True)
                cancel_flow = builder(provider="codex", model=model.id, effort=effort, runner_url="http://127.0.0.1:" + str(server.server_port), task="Use the shell to sleep for 45 seconds, then reply done. Do not edit files or delegate.")
                cancel_graph = Graph.from_payload(cancel_flow, flow_id=str(uuid4()), user_id=owner)
                async def stop_graph():
                    task = asyncio.create_task(cancel_graph.arun(inputs=[{}],outputs=["agent"]))
                    deadline = time.monotonic() + 90
                    run_id = None
                    while time.monotonic() < deadline and not task.done():
                        for path in (agent.state / "runs").glob("*/record.json"):
                            item = json.loads(path.read_text())
                            if item["run_id"] != record["run_id"] and item.get("status") == "running":
                                run_id = item["run_id"]
                                break
                        if run_id:
                            break
                        await asyncio.sleep(.2)
                    assert run_id, "cancel_run_not_active"
                    await asyncio.sleep(3)
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
                    deadline = time.monotonic() + 120
                    while time.monotonic() < deadline:
                        current = agent.status(run_id)
                        if current["status"] in {"cancelled","completed","failed","timeout","interrupted"}:
                            break
                        await asyncio.sleep(.2)
                    await asyncio.sleep(2)
                    print(json.dumps({"stage":"graph_stop", "status":current["status"], "cancel_confirmed":current.get("cancel_confirmed")}),flush=True)
                    assert current["status"] == "cancelled" and current.get("cancel_confirmed") is True, "graph_stop_not_confirmed"
                asyncio.run(stop_graph())
            finally:
                if server is not None:
                    server.shutdown()
                    server.server_close()
                supervisor.terminate()
                supervisor.wait(timeout=20)

if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Do not print native responses, credentials, or private runtime state.
        print(json.dumps({"stage":"failed", "type":type(error).__name__, "code":getattr(error,"code",None), "assertion":str(error) if isinstance(error,AssertionError) else None}),flush=True)
        raise SystemExit(1)
