"""Explicitly approved direct-CLI diagnostic; private output and shared turn ledger."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from laomedo.local_runner import _json


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--approved-model-turn", action="store_true")
    parser.add_argument("--cumulative-cap", type=int, required=True)
    args = parser.parse_args()
    if not args.approved_model_turn:
        parser.error("explicit approval required")
    state = Path(os.environ["LOCALAPPDATA"]) / "Laomedo/opencode-27"
    ledger_path = state / "runs-state/turn-ledger.json"
    ledger = json.loads(ledger_path.read_text())
    if args.cumulative_cap < ledger["max_authorized_turns"] or ledger["attempted_turns"] >= args.cumulative_cap:
        raise RuntimeError("model_turn_cap_reached")
    ledger["max_authorized_turns"] = args.cumulative_cap
    ledger["attempted_turns"] += 1
    _json(ledger_path, ledger)
    attempt = ledger["attempted_turns"]
    environment = dict(os.environ)
    environment["OPENCODE_PERMISSION"] = '{"*":"deny"}'
    command = ["opencode.cmd", "run", "--pure", "--format", "json",
        "--model", "opencode-go/gpt-6-luna", "--dir", str(ROOT),
        "--title", "Laomedo direct CLI authentication diagnostic",
        "Do not call any tool or inspect any file. Reply with exactly OPENCODE_CLI_27_REACHABLE."]
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=environment)
    timed_out = False
    try:
        stdout, stderr = process.communicate(timeout=180)
    except subprocess.TimeoutExpired:
        timed_out = True
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
        stdout, stderr = process.communicate(timeout=15)
    (state / f"direct-cli-{attempt}.stdout.jsonl").write_bytes(stdout)
    (state / f"direct-cli-{attempt}.stderr.log").write_bytes(stderr)
    events = []
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    texts = [event.get("part", {}).get("text", "") for event in events if event.get("type") == "text"]
    summary = {"attempt": attempt, "exit_code": process.returncode, "timed_out": timed_out,
        "event_types": sorted({event.get("type", "unknown") for event in events}),
        "exact_marker_observed": "OPENCODE_CLI_27_REACHABLE" in texts,
        "tools_observed": sum(event.get("type") == "tool_use" for event in events),
        "boundary": "Direct personal CLI login diagnostic; not isolated runner acceptance."}
    _json(state / f"direct-cli-{attempt}-summary.json", summary)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
