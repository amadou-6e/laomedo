"""Authorized isolated Claude acceptance; only safe aggregates leave temporary state."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import build_opener, ProxyHandler
from uuid import uuid4


def observe(
    agent, server, store, operation, model, effort, previous=None, cancel_ready=None
):
    from laomedo.agents.activity.capture import ActivityCapture
    from laomedo.agents.activity.models import CaptureIdentity, ActivityInvocation
    from laomedo.agents.activity.projection import project
    from laomedo.agents.errors import RunnerError

    attempt = str(uuid4()) if previous else None
    run_id = previous["run_id"] if previous else None
    task = (
        "Use the shell to sleep for 45 seconds, then repeat the acceptance marker. Do not edit files or delegate."
        if operation == "cancel"
        else (
            "What acceptance marker did you just read? Reply only with the marker. Do not use tools or delegate."
            if previous
            else "Read task.txt and reply only with the acceptance marker. Do not edit files or delegate."
        )
    )
    results, errors, cancellation = [], [], {}

    def execute():
        try:
            if previous:
                results.append(
                    agent.resume(
                        run_id,
                        task,
                        expected_post_run_hash=previous["post_run_hash"],
                        expected_thread_id=previous["thread_id"],
                        model=model,
                        effort=effort,
                        activity_attempt_id=attempt,
                    )
                )
            else:
                results.append(
                    agent.start({"task": task, "model": model, "effort": effort})
                )
        except RunnerError as error:
            errors.append(error.code)
        except Exception as error:
            errors.append(type(error).__name__)

    worker = threading.Thread(target=execute)
    worker.start()
    observer = None
    cancel_worker = None
    try:
        deadline = time.monotonic() + 240
        while run_id is None and worker.is_alive() and time.monotonic() < deadline:
            candidates = list((agent.state / "runs").glob("*/record.json"))
            if candidates:
                try:
                    record = json.loads(candidates[0].read_text())
                except (OSError, ValueError):
                    time.sleep(0.1)
                    continue
                run_id, attempt = (
                    record["run_id"],
                    record["activity_initial_attempt_id"],
                )
                break
            time.sleep(0.1)
        if not run_id:
            print(
                json.dumps(
                    {"stage": operation, "worker_errors": errors, "admitted": False}
                ),
                flush=True,
            )
            raise RuntimeError("run_not_admitted")
        invocation = store.start(
            CaptureIdentity.from_values(
                "acceptance-owner", "flow", operation, provider=agent.provider
            )
        )
        capture = ActivityCapture.__new__(ActivityCapture)
        capture.capture = ActivityInvocation(store=store, invocation_id=invocation)
        capture.timeout, capture.attempt_id, capture.accepted = 240, attempt, False
        capture.refused, capture.done = threading.Event(), threading.Event()
        capture.outcome = None
        capture.base = "http://127.0.0.1:" + str(server.server_port)
        capture.token = agent.api_token
        capture.opener = build_opener(ProxyHandler({}))

        def settled():
            worker.join()
            capture.outcome = results[0]["status"] if results else "failed"
            capture.done.set()

        observer = threading.Thread(target=settled, daemon=True)
        observer.start()

        def cancel_active_tool():
            active_tool = False
            until = time.monotonic() + 90
            while worker.is_alive() and time.monotonic() < until:
                page = agent.read_activity(run_id, attempt)
                if (
                    cancel_ready()
                    if cancel_ready
                    else any(row.event.kind == "tool_call" for row in page.records)
                ):
                    active_tool = True
                    break
                time.sleep(0.25)
            cancellation["active_tool_observed"] = active_tool
            if worker.is_alive():
                cancellation["requested"] = bool(
                    agent.cancel(run_id).get("cancel_requested")
                )

        if operation == "cancel":
            cancel_worker = threading.Thread(target=cancel_active_tool, daemon=True)
            cancel_worker.start()
        capture.observe(run_id)
        worker.join(timeout=240)
        if cancel_worker:
            cancel_worker.join(timeout=10)
        if worker.is_alive() or errors or not results:
            print(
                json.dumps(
                    {
                        "stage": operation,
                        "worker_errors": errors,
                        "settled": not worker.is_alive(),
                    }
                ),
                flush=True,
            )
            raise RuntimeError("execution_not_settled")
        result = results[0]
        saved = store.read("acceptance-owner", "flow", operation, invocation)
        view = project(saved["events"], provider="unused-common-path")
        first = agent.read_activity(run_id, attempt, limit=1)
        replay = agent.read_activity(run_id, attempt, limit=1)
        page, count = first, 0
        while True:
            count += len(page.records)
            if not page.has_more:
                break
            page = agent.read_activity(run_id, attempt, after=page.next_after, limit=1)
        checks = {
            "stage": operation,
            "provider": agent.provider,
            "status": result["status"],
            "error": result.get("error_category"),
            "capture_reason": page.reason,
            "closed": page.closed,
            "complete": page.complete,
            "stream_state": saved["run"]["stream_state"],
            "record_count": count,
            "item_count": len(view["items"]),
            "stable_replay": first.records == replay.records,
            "thread_preserved": previous is None
            or result.get("thread_id") == previous.get("thread_id"),
            "cancel_confirmed": result.get("cancel_confirmed"),
            **cancellation,
        }
        if operation != "cancel":
            checks["answer_ok"] = "amber-277" in (result.get("answer") or "")
        print(json.dumps(checks), flush=True)
        expected = "cancelled" if operation == "cancel" else "completed"
        if (
            result["status"] != expected
            or not page.complete
            or not count
            or not checks["stable_replay"]
            or not checks["thread_preserved"]
        ):
            raise RuntimeError("claude_activity_acceptance_failed")
        if operation == "cancel" and not (
            cancellation.get("active_tool_observed")
            and cancellation.get("requested")
            and result.get("cancel_confirmed")
        ):
            raise RuntimeError("claude_cancellation_acceptance_failed")
        if operation != "cancel" and not checks["answer_ok"]:
            raise RuntimeError("claude_answer_acceptance_failed")
        return result
    finally:
        if worker.is_alive() and run_id:
            agent.cancel(run_id)
            worker.join(timeout=120)
        if cancel_worker:
            cancel_worker.join(timeout=10)
        if observer:
            observer.join(timeout=5)
        if worker.is_alive():
            raise RuntimeError("claude_worker_cleanup_unconfirmed")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation", type=Path, required=True)
    parser.add_argument("--mirror-host-login", action="store_true", required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.implementation / "src"))
    from laomedo.agents.agents.claude.agent import ClaudeAgent
    from laomedo.agents.activity.store import ActivityStore
    from laomedo.host.runner.http.server import RunnerServer
    from laomedo.agents.errors import RunnerError

    profile = "laomedo-claude-acceptance-" + uuid4().hex
    previous_flag = os.environ.get("LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN")
    os.environ["LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN"] = "1"
    server = http = supervisor = log = temporary = None
    try:
        temporary = tempfile.TemporaryDirectory(prefix="laomedo-claude-acceptance-")
        root = Path(temporary.name)
        source = root / "repository/source"
        source.mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet", str(source.parent)], check=True)
        (source / "task.txt").write_text("Acceptance marker: amber-277.\n")
        lease = root / "lease"
        log = (root / "supervisor.log").open("wb")
        supervisor = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "laomedo.host.leases.service_cli",
                "serve",
                "--state",
                str(lease),
            ],
            env=dict(os.environ, PYTHONPATH=str(args.implementation / "src")),
            stdout=log,
            stderr=log,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        until = time.monotonic() + 20
        while not (lease / "service.json").exists():
            if supervisor.poll() is not None or time.monotonic() > until:
                raise RuntimeError("lease_service_start_failed")
            time.sleep(0.1)
        agent = ClaudeAgent(
            root / "runner",
            root / "registry",
            source,
            lease_service=lease,
            profile_volume=profile,
        )
        print(
            json.dumps(
                {"stage": "admission", "provider": "claude", "image_id": agent.image_id}
            ),
            flush=True,
        )
        ready = agent.readiness()
        print(
            json.dumps(
                {
                    "stage": "readiness",
                    "ready": ready.ready,
                    "reason": ready.reason,
                    "scope": ready.scope,
                }
            ),
            flush=True,
        )
        if ready.ready is not True:
            return
        catalog = agent.model_catalog(refresh=True)
        selected = next(
            (value for value in catalog["models"] if value["id"] == "sonnet"), None
        )
        if selected is None:
            raise RuntimeError("claude_sonnet_model_not_available")
        model = selected["id"]
        effort = "low" if "low" in selected.get("efforts", []) else "default"
        print(
            json.dumps(
                {
                    "stage": "discovery",
                    "provider": "claude",
                    "model_count": len(catalog["models"]),
                    "selected_model": model,
                    "effort": effort,
                }
            ),
            flush=True,
        )
        server = RunnerServer(agent, port=0)
        http = threading.Thread(target=server.serve_forever, daemon=True)
        http.start()
        store = ActivityStore(root / "application.db")
        fresh = observe(agent, server, store, "fresh", model, effort)
        resumed = observe(agent, server, store, "resume", model, effort, fresh)
        observe(agent, server, store, "cancel", model, effort, resumed)
    except RunnerError as error:
        print(
            json.dumps({"stage": "blocked", "provider": "claude", "code": error.code}),
            flush=True,
        )
    finally:
        if server:
            server.shutdown()
            http.join(timeout=5)
            server.server_close()
        if supervisor:
            supervisor.terminate()
            supervisor.wait(timeout=15)
        if log:
            log.close()
        removed = subprocess.run(
            ["docker", "volume", "rm", profile],
            capture_output=True,
            timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        print(
            json.dumps(
                {
                    "stage": "temporary_profile_cleanup",
                    "removed": removed.returncode == 0,
                }
            ),
            flush=True,
        )
        if previous_flag is None:
            os.environ.pop("LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN", None)
        else:
            os.environ["LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN"] = previous_flag
        if temporary:
            temporary.cleanup()


if __name__ == "__main__":
    main()
