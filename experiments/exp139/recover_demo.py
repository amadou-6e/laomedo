"""Prepare a reviewed demo amendment without resetting any durable budget."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import socket
import sqlite3
import subprocess

from experiments.exp139.prepare import ROOT; from experiments.exp139.prepare import LANGFLOW; from experiments.exp139.prepare import report_task; from experiments.exp139.prepare import save
from experiments.exp139.runtime import configuration


def recover(root):
    root, config = configuration(root)
    if config["identity"] != "langflow-demo-20261012-c":
        raise ValueError("interactive_campaign_required")
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", 8779)) == 0:
            raise ValueError("stop_campaign_before_amending")
    ledger_path = root / "runner/turn-ledger.json"
    ledger = ledger_path.read_bytes()
    used = json.loads(ledger)["attempted_turns"]
    if not 1 <= used < 4:
        raise ValueError("remaining_campaign_turn_required")
    with sqlite3.connect("file:" + (root / "host/write-budget.sqlite").as_posix() + "?mode=ro", uri=True) as db:
        if db.execute("SELECT COUNT(*) FROM attempts").fetchone()[0]:
            raise ValueError("publication_budget_already_used")
    archive = root / "amendments" / sha256((root / "manifest.json").read_bytes()).hexdigest()
    archive.mkdir(parents=True, exist_ok=False)
    for name in ("config.json", "manifest.json", "activation.json", "flow-input/inputs.json", "flow-input/success.json"):
        target = archive / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((root / name).read_bytes())
    inputs = json.loads((root / "flow-input/inputs.json").read_bytes())
    # The frozen report bytes are recovered from the original task's JSON
    # string, rather than fetching or modifying the selected issue.
    original = inputs["tasks"]["success"]
    marker = "with these exact UTF-8 bytes: "
    if marker not in original:
        raise ValueError("original_exact_report_required")
    report, _ = json.JSONDecoder().raw_decode(original.split(marker, 1)[1])
    if sha256(report.encode()).hexdigest() != config["report_sha256"]:
        raise ValueError("frozen_report_mismatch")
    inputs["tasks"]["success"] = report_task(report, config["branch"])
    save(root / "flow-input/inputs.json", inputs)
    script = """import importlib.util,json
from pathlib import Path
spec=importlib.util.spec_from_file_location('builder','/work/examples/langflow-workgraph-live/build_flow.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)
data=json.loads(Path('/input/inputs.json').read_bytes())
flow=builder.build(data['snapshot'],data['tasks']['success'],runner_url='http://host.docker.internal:8779')
Path('/input/success.json').write_text(json.dumps(flow,indent=2)+'\\n')
"""
    subprocess.run(["docker", "run", "--rm", "--pull=never", "--network", "none",
        "--mount", f"type=bind,source={ROOT},target=/work,readonly",
        "--mount", f"type=bind,source={root / 'flow-input'},target=/input",
        "--env", "PYTHONPATH=/work", "--entrypoint", "python", LANGFLOW, "-c", script],
        check=True, timeout=90, capture_output=True)
    if ledger_path.read_bytes() != ledger:
        raise ValueError("ledger_changed_during_preparation")
    result = {"prepared_only": True, "prior_used_turns": used, "total_turn_cap": 4,
              "push_attempts": 0, "draft_pr_attempts": 0, "archive": str(archive)}
    save(root / "amendment-preparation.json", result)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", required=True, type=Path)
    print(json.dumps(recover(parser.parse_args().state.resolve())))
