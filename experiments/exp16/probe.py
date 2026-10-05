"""EXP-16: compare frozen mock-dispatch decisions with a separate oracle."""

import argparse
from datetime import datetime
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import sys

from laomedo.work_graph.github import import_pages
from laomedo.work_graph.model import GraphSnapshot
from laomedo.workflow_run_store import ExternalOutcomeUnknown, WorkflowRunStore


HERE = Path(__file__).resolve().parent
REPOSITORY = "verify/exp16"
SELECTED = "github:S-20"
NOW = "2026-10-05T10:00:00+00:00"
FETCHED_AT = NOW
FLOW = {"nodes": [{"id": "mock-stage"}], "edges": []}
COMPONENT_CODE = {"mock-stage": "exp16-synthetic-component-v1"}


class Refusal(ValueError):
    pass


def digest(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"),
                         ensure_ascii=False).encode("utf-8")
    return "sha256:" + sha256(encoded).hexdigest()


def file_hash(path):
    return sha256(path.read_bytes()).hexdigest()


def outside_git(path):
    for parent in (path, *path.parents):
        if (parent / ".git").exists():
            raise ValueError("Output directory must be outside a Git working tree")


def evidence_store(path):
    # Load an existing experiment store by file path without adding the source
    # checkout to sys.path; laomedo must still resolve from the installed wheel.
    source = HERE.parent / "exp05" / "evidence.py"
    spec = importlib.util.spec_from_file_location("exp16_evidence", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.EvidenceStore(path)


def item(graph):
    return next((value for value in graph.items if value.key == SELECTED), None)


def mock_grant(graph, variant):
    grant = {"grant_id": "exp16-synthetic-grant", "authorized": True,
             "runner": "mock-runner", "work_key": SELECTED,
             "graph_snapshot_id": graph.snapshot_id,
             "expires_at": "2026-10-05T10:10:00+00:00"}
    if variant == "expired":
        grant["expires_at"] = "2026-10-05T09:59:00+00:00"
    elif variant == "wrong_work":
        grant["work_key"] = "github:I-30"
    elif variant == "wrong_graph":
        grant["graph_snapshot_id"] = "sha256:" + "0" * 64
    elif variant == "wrong_runner":
        grant["runner"] = "other-runner"
    elif variant == "unauthorized":
        grant["authorized"] = False
    elif variant != "valid":
        raise ValueError("Unknown grant fixture")
    return grant


def preflight(frozen, current, case):
    changed = frozen.snapshot_id != current.snapshot_id
    choice = case.get("choice")
    if changed and choice not in {"pinned", "refreshed"}:
        raise Refusal("stale_unacknowledged")
    if not current.source_complete:
        raise Refusal("source_incomplete")
    selected = item(current)
    if selected is None or selected.state != "OPEN":
        raise Refusal("selected_item_unavailable")
    readiness = current.readiness()[SELECTED]
    if readiness == "unknown":
        raise Refusal("prerequisite_unknown")
    if readiness == "cyclic":
        raise Refusal("prerequisite_cyclic")
    override = case.get("override")
    if readiness == "blocked":
        if override is None:
            raise Refusal("open_prerequisite")
        if (not isinstance(override.get("rationale"), str)
                or not override["rationale"].strip()
                or not override.get("prerequisite")
                or override.get("dependent") != SELECTED):
            raise Refusal("override_incomplete")
        open_edges = {(edge.prerequisite, edge.dependent)
                      for edge in current.dependencies if edge.dependent == SELECTED
                      and any(node.key == edge.prerequisite and node.state == "OPEN"
                              for node in current.items)}
        if open_edges != {(override["prerequisite"], override["dependent"])}:
            raise Refusal("override_wrong_edge")
    elif readiness != "ready" or override is not None:
        raise Refusal("override_not_applicable")
    bound = current if choice == "refreshed" else frozen
    grant = mock_grant(bound, case.get("grant", "valid"))
    if not grant["authorized"]:
        raise Refusal("grant_unauthorized")
    if datetime.fromisoformat(grant["expires_at"]) <= datetime.fromisoformat(NOW):
        raise Refusal("grant_expired")
    if grant["work_key"] != SELECTED:
        raise Refusal("grant_wrong_work")
    if grant["graph_snapshot_id"] != bound.snapshot_id:
        raise Refusal("grant_wrong_graph")
    if grant["runner"] != "mock-runner":
        raise Refusal("grant_wrong_runner")
    return bound, grant, choice or "unchanged", override


def run_case(root, name, frozen, current, case):
    case_root = root / name
    case_root.mkdir()
    database = case_root / "run.sqlite3"
    runs = WorkflowRunStore(database)
    evidence = evidence_store(database)
    projection = {}
    if case.get("filter_label"):
        view = current.project("open", (case["filter_label"],))
        matches = {value["key"]: value["readiness"] for value in view["items"]}
        projection = {
            "projection_readiness": matches.get(SELECTED),
            "context_edge": any(edge["dependent"] == SELECTED and
                                edge["prerequisite"] == "github:C-10"
                                for edge in view["context_dependencies"]),
        }
    try:
        bound, grant, choice, override = preflight(frozen, current, case)
    except Refusal as error:
        counters = runs.counters()
        actual = {"outcome": "refused", "calls": 0, "reason": str(error),
                  **projection}
        checks = {"zero_runs": counters["runs"] == 0,
                  "zero_dispatch_attempts": counters["dispatch_attempts"] == 0,
                  "zero_mock_calls": counters["synthetic_dispatches"] == 0}
        return actual, checks

    selected = item(bound)
    work_snapshot = {"key": selected.key, "repository": selected.repository,
                     "number": selected.number, "url": selected.url,
                     "updated_at": selected.updated_at,
                     "body_digest": digest(selected.body)}
    frozen_input = {"work": work_snapshot, "body": selected.body,
                    "graph_snapshot_id": bound.snapshot_id}
    trigger = {"work_snapshot": work_snapshot,
               "work_snapshot_id": digest(work_snapshot),
               "graph_snapshot_id": bound.snapshot_id,
               "input_digest": digest(frozen_input), "source_choice": choice,
               "override": override, "grant_id": grant["grant_id"]}
    config = {"provider": "mock", "model": "none", "effort": "none",
              "grant": grant, "turn_cap": 0}
    artifact = bound.save(case_root / "snapshots")
    run = runs.reserve(graph=FLOW, component_code=COMPONENT_CODE,
                       resolved_config=config, trigger=trigger)
    invocation = "exp16-" + run["run_id"]
    evidence.reserve(run_id=run["run_id"], trace_id=run["trace_id"],
                     stage_id="mock-stage", invocation_id=invocation)
    binding = {**trigger, "run_id": run["run_id"], "trace_id": run["trace_id"],
               "definition_revision": run["graph_revision"],
               "component_revision": run["component_revisions"]["mock-stage"]}

    def mock_runner(run_id):
        runs.record_synthetic_dispatch(run_id)
        evidence.record_native_session(invocation, "mock-session-" + run_id)
        evidence.append_raw_event(invocation, source_event_id="input", kind="input",
                                  payload={"summary": "frozen input received",
                                           "binding": binding})
        if case.get("mock") == "rejected":
            raise RuntimeError("mock_runner_rejected")
        if case.get("mock") == "unknown":
            raise ExternalOutcomeUnknown("mock_result_unknown")
        evidence.append_raw_event(invocation, source_event_id="result", kind="result",
                                  payload={"summary": "mock result", "run_id": run_id})
        evidence.project_unprojected()
        evidence.mark_complete(invocation)
        return {"mock_result": "completed"}

    try:
        runs.dispatch(run["run_id"], mock_runner)
    except (RuntimeError, ExternalOutcomeUnknown) as error:
        if str(error) not in {"mock_runner_rejected", "mock_result_unknown"}:
            raise
        evidence.sweep_crashed()
    stored = runs.get(run["run_id"])
    observed = evidence.inspect()
    raw = [value for value in observed["raw_events"]
           if value["invocation_id"] == invocation]
    invocation_state = next(value for value in observed["invocations"]
                            if value["invocation_id"] == invocation)
    raw_binding = json.loads(raw[0]["payload_json"])["binding"] if raw else None
    counters = runs.counters()
    checks = {
        "one_run": counters["runs"] == 1,
        "one_attempt": counters["dispatch_attempts"] == 1,
        "one_mock_call": counters["synthetic_dispatches"] == 1,
        "trigger_retained": json.loads(stored["trigger_json"]) == trigger,
        "grant_and_config_retained": json.loads(stored["resolved_config"]) == config,
        "raw_binding_retained": raw_binding == binding,
        "definition_revision_retained": stored["graph_revision"] == digest(FLOW),
        "component_revision_retained": binding["component_revision"] ==
            "sha256:" + sha256(COMPONENT_CODE["mock-stage"].encode("utf-8")).hexdigest(),
        "snapshot_retained": GraphSnapshot.from_dict(
            json.loads(artifact.read_text(encoding="utf-8"))).snapshot_id == bound.snapshot_id,
        "trace_identity_retained": invocation_state["run_id"] == run["run_id"]
            and invocation_state["trace_id"] == run["trace_id"],
        "partial_not_fabricated": (stored["status"] == "completed"
            or (invocation_state["stream_state"] == "partial"
                and not bool(stored["evidence_complete"]))),
    }
    actual = {"outcome": stored["status"], "calls": counters["synthetic_dispatches"],
              "selection": case["current"] if choice == "refreshed" else "base",
              "choice": choice, "override": override is not None,
              "trace": invocation_state["stream_state"],
              "run_id": run["run_id"], "trace_id": run["trace_id"],
              "graph_snapshot_id": bound.snapshot_id,
              "input_digest": trigger["input_digest"], **projection}
    return actual, checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    outside_git(output)
    if output.exists():
        raise ValueError("Output directory must be fresh")
    output.mkdir(parents=True)
    corpus_path = HERE / "corpus.json"
    cases_path = HERE / "cases.json"
    oracle_path = HERE / "oracle.json"
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    cases = json.loads(cases_path.read_text(encoding="utf-8"))
    oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    if set(cases) != set(oracle):
        raise ValueError("Case list and oracle differ")
    snapshots = {name: import_pages(REPOSITORY, pages, FETCHED_AT)
                 for name, pages in corpus.items()}
    frozen = snapshots["base"]
    results = {}
    for name, case in cases.items():
        actual, checks = run_case(output, name, frozen, snapshots[case["current"]], case)
        expected = oracle[name]
        compared = {key: actual.get(key) for key in expected}
        results[name] = {"passed": compared == expected and all(checks.values()),
                         "expected": expected, "observed": actual, "checks": checks,
                         "source_snapshot_id": snapshots[case["current"]].snapshot_id}
    import laomedo
    report = {"corpus_sha256": file_hash(corpus_path),
              "cases_sha256": file_hash(cases_path),
              "oracle_sha256": file_hash(oracle_path),
              "installed_package_path": str(Path(laomedo.__file__).resolve()),
              "connector_version": frozen.connector_version,
              "schema_version": frozen.schema_version,
              "model_turns": 0, "github_writes": 0, "cases": results,
              "passed": all(value["passed"] for value in results.values())}
    result = output / "result.json"
    result.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    print(json.dumps({"passed": report["passed"],
                      "cases": {name: value["passed"] for name, value in results.items()},
                      "result": str(result)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
