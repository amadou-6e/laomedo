"""No-model browser Stop gate against the installed flow and fake runner."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4

from experiments.exp22.phase_c_live import _stop
from experiments.exp22.phase_d_live import LANGFLOW_IMAGE, ROOT, _port, _private_empty
from experiments.exp22.phase_e_ui import BROWSER, _remove_ui, _wait_ui


def _rows(path):
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()]


def _wait(path, seconds=10):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if path.exists():
            return
        time.sleep(.05)
    raise RuntimeError("fake_runner_token_missing")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", required=True, type=Path)
    args = parser.parse_args()
    state = _private_empty(args.state)
    fake_state = state / "fake-runner"
    fake_state.mkdir()
    (state / "langflow-data").mkdir()
    runner_port, ui_port = _port(), _port()
    name = "laomedo-phase-e-fake-" + uuid4().hex[:16]
    fake_log = (state / "fake-runner.log").open("w", encoding="utf-8")
    browser_log = (state / "browser.log").open("w", encoding="utf-8")
    fake = subprocess.Popen([sys.executable, "-m", "experiments.exp94.fake_runner",
                             "--state", str(fake_state), "--port", str(runner_port)],
                            cwd=ROOT, stdout=fake_log, stderr=subprocess.STDOUT)
    browser = None
    teardown = {"ui_container_absent": None, "fake_runner_stopped": None}
    try:
        _wait(fake_state / "api-token")
        command = ["docker", "run", "-d", "--rm", "--pull=never", "--name", name,
                   "-p", f"127.0.0.1:{ui_port}:7860", "--cap-drop", "ALL",
                   "--security-opt", "no-new-privileges",
                   "--mount", f"type=bind,source={ROOT / 'components'},target=/app/custom_components,readonly",
                   "--mount", (f"type=bind,source={fake_state / 'api-token'},"
                               "target=/run/secrets/laomedo-runner-token,readonly"),
                   "--mount", f"type=bind,source={state / 'langflow-data'},target=/app/langflow",
                   "-e", "LANGFLOW_COMPONENTS_PATH=/app/custom_components",
                   "-e", "LANGFLOW_AUTO_LOGIN=true", "-e", "DO_NOT_TRACK=true",
                   "-e", "LAOMEDO_RUNNER_TOKEN_FILE=/run/secrets/laomedo-runner-token",
                   LANGFLOW_IMAGE]
        started = subprocess.run(command, capture_output=True, timeout=30)
        if started.returncode != 0:
            raise RuntimeError("fake_langflow_start_failed")
        _wait_ui(ui_port)
        revision = "sha256:" + "a" * 64
        base = ["node", str(BROWSER), "prepare", str(state), str(ui_port),
                str(runner_port), revision]
        prepared = subprocess.run(base, capture_output=True, timeout=90)
        if prepared.returncode != 0:
            raise RuntimeError("fake_playground_prepare_failed")
        env = dict(os.environ, PHASE_E_FAKE_PREFLIGHT="1")
        browser = subprocess.Popen(["node", str(BROWSER), "run", str(state),
                                    str(ui_port), str(runner_port), revision],
                                   cwd=ROOT, env=env, stdout=browser_log,
                                   stderr=subprocess.STDOUT)
        journal = fake_state / "journal.jsonl"
        deadline = time.monotonic() + 35
        while time.monotonic() < deadline:
            if any(row.get("kind") == "synthetic_wait_started" for row in _rows(journal)):
                break
            if browser.poll() is not None:
                raise RuntimeError("fake_browser_exited_before_wait")
            time.sleep(.1)
        else:
            raise RuntimeError("fake_wait_not_observed")
        (state / "stop-now.signal").write_text("stop", encoding="ascii")
        deadline = time.monotonic() + 25
        while time.monotonic() < deadline:
            if any(row.get("kind") == "cancel_received" for row in _rows(journal)):
                (state / "runner-terminal.signal").write_text("terminal", encoding="ascii")
                break
            time.sleep(.1)
        browser.wait(timeout=50)
        observed = json.loads((state / "browser-run.json").read_text(encoding="utf-8"))
        # CASE_B schedules its synthetic effect six seconds after start.
        time.sleep(7)
        rows = _rows(journal)
        kinds = [row.get("kind") for row in rows]
        starts = [row for row in rows if row.get("kind") == "post_received"]
        cancels = [row for row in rows if row.get("kind") == "cancel_received"]
        lookups = [row for row in rows if row.get("kind") == "request_lookup"]
        token = (fake_state / "api-token").read_text(encoding="ascii").strip()
        token_leaked = token in (state / "browser-run.json").read_text(encoding="utf-8")
        passed = (browser.returncode == 0 and observed.get("send_clicked") and
                  observed.get("stop_clicked") and observed.get("stop_signal_seen") and
                  observed.get("runner_terminal_signal_seen") and len(starts) == 1 and
                  len(cancels) == 1 and len(lookups) >= 1 and
                  starts[0]["run_id"] == cancels[0]["run_id"] == lookups[0]["run_id"]
                  and "synthetic_effect" not in kinds and not token_leaked)
        summary = {"passed": passed, "model_turn_submitted": False,
                   "visible_stop_clicked": observed.get("stop_clicked"),
                   "starts": len(starts), "lookups": len(lookups),
                   "cancels": len(cancels), "late_effects": kinds.count("synthetic_effect"),
                   "fake_token_in_browser_result": token_leaked}
        (state / "sanitized.json").write_text(json.dumps(summary, indent=2),
                                                 encoding="utf-8")
        print(json.dumps(summary))
        if not passed:
            raise RuntimeError("fake_visible_stop_gate_failed")
    finally:
        if browser and browser.poll() is None:
            _stop(browser, tree=True)
        try:
            teardown["ui_container_absent"] = _remove_ui(name)
        except Exception as exc:
            teardown["ui_cleanup_error"] = type(exc).__name__
        fake.terminate()
        try:
            fake.wait(timeout=5)
        except subprocess.TimeoutExpired:
            fake.kill()
            fake.wait(timeout=5)
        teardown["fake_runner_stopped"] = fake.poll() is not None
        (state / "teardown.json").write_text(json.dumps(teardown, indent=2),
                                              encoding="utf-8")
        fake_log.close()
        browser_log.close()


if __name__ == "__main__":
    main()
