"""Machine-written, credential-free evidence from the serialized imported graph."""
import asyncio
import hashlib
import importlib.util
import json
from pathlib import Path
import os
import re
from importlib.metadata import version

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("demo_tests", ROOT / "tests/langflow/test_workgraph_demo.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
IMAGE = "sha256:34055a07d446de51760e28dab6332e22624e5f48dca611567779992fc32c5ec0"


async def main():
    source_commit = os.environ.get("LAOMEDO_DEMO_SOURCE_COMMIT", "")
    if not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("full_frozen_source_commit_required")
    expected = json.loads((HERE / "expectations.json").read_text())
    cases = {
        "valid_success": ({"task_outcome": "success", "report": "fixture complete"}, {}),
        "valid_task_failure": ({"task_outcome": "failure", "report": "cannot finish fixture"}, {}),
        "invalid_submission": ({"task_outcome": "success"}, {}),
        "precheck_correction": ({"task_outcome": "success"}, {"correction": "within_request"}),
        "exhausted_correction": ({"task_outcome": "success"}, {"correction": "exhausted"}),
        "runtime_interruption": ({"task_outcome": "unknown"}, {"status": "interrupted"})}
    evidence = []
    for name, (submission, options) in cases.items():
        results, calls = await probe.run_case(submission, **options)
        routed = probe.records(results)
        assert len(routed) == 1, (name, len(routed))
        record = routed[0]
        observed = {"destination": record["destination"],
                    "contract_status": record["routed"]["validation"]["contract_status"],
                    "publication_mode": (record["publication"] or {}).get("mode"),
                    "continuations": calls[0].get("fixture_continuations", 0)}
        assert observed == expected[name], (name, observed)
        evidence.append({"case": name, "expected": expected[name], "observed": observed,
                         "record": record, "fixture_prechecks": calls[0].get("fixture_prechecks", []),
                         "runner_dispatches": len(calls), "evidence_source": "fixture_runner_script"})
    paths = [HERE / name for name in ("flow.json", "fixtures.json", "expectations.json", "build_flow.py",
                                     "fixture_issue.py", "route.py", "destination.py", "acceptance.py")]
    paths += [ROOT / "tests/langflow/test_workgraph_demo.py"]
    paths += [HERE / "skill/SKILL.md"]
    report = {"schema_version": 1, "langflow_version": version("langflow"), "lfx_version": version("lfx"),
              "image_digest": IMAGE, "model_turns": 0, "github_writes": 0,
              "real_credentials": False, "publication": "simulated_only",
              "source_commit": source_commit,
              "artifact_sha256": {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths},
              "limits": ["Fake runner responses, not native model behavior.",
                         "Precheck/continuation sequence is scripted fixture behavior using the real evaluator.",
                         "No real PR, real account connection, filesystem preservation, or live credentials tested."],
              "cases": evidence}
    (HERE / "evidence.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("six_imported_graph_cases_passed")


if __name__ == "__main__":
    asyncio.run(main())
