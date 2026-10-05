"""Compose existing stores with a fake agent and a local Git candidate only."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from experiments.exp05.evidence import EvidenceStore
from laomedo.work_graph.github import import_pages
from laomedo.workflow_run_store import WorkflowRunStore


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "examples" / "work-graph" / "github-pages.json"
FETCHED_AT = "2026-10-01T08:00:00+00:00"
WORK_KEY = "github:I_2"
FLOW = {"nodes": [{"id": "issue-input"}, {"id": "fake-agent"}],
        "edges": [{"source": "issue-input", "target": "fake-agent"}]}
COMPONENT_CODE = {"issue-input": "fixture-issue-input-v1",
                  "fake-agent": "fixture-fake-agent-v1"}
SKILL_BYTES = b"Synthetic skill for EXP-19. Do not invoke a model.\n"


def digest(data: bytes) -> str:
    return "sha256:" + sha256(data).hexdigest()


def _pages() -> list[dict]:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _graph(pages: list[dict]):
    return import_pages("example/work", pages, fetched_at=FETCHED_AT)


def _item(graph):
    return next(item for item in graph.items if item.key == WORK_KEY)


def _frozen_input(graph) -> dict:
    item = _item(graph)
    return {"work_key": item.key, "url": item.url,
            "updated_at": item.updated_at,
            "body_digest": digest(item.body.encode("utf-8")),
            "graph_snapshot_id": graph.snapshot_id}


def _gate(frozen: dict, current) -> None:
    if not current.source_complete or current.readiness().get(WORK_KEY) != "ready":
        raise ValueError("source_not_ready")
    if current.snapshot_id != frozen["graph_snapshot_id"]:
        raise ValueError("source_snapshot_changed")
    if _frozen_input(current) != frozen:
        raise ValueError("source_input_changed")


def _git(directory: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(directory), *args],
                            text=True, capture_output=True, encoding="utf-8",
                            check=True, timeout=20)
    return result.stdout.strip()


def _local_candidate(directory: Path, binding: dict) -> dict:
    directory.mkdir(parents=True, exist_ok=False)
    _git(directory, "init", "-b", "main")
    _git(directory, "config", "user.name", "EXP-19 Fake Agent")
    _git(directory, "config", "user.email", "exp19@example.invalid")
    branch = "exp19/" + binding["run_id"]
    _git(directory, "switch", "-c", branch)
    output = directory / "result.json"
    output.write_text(json.dumps(binding, sort_keys=True, indent=2) + "\n",
                      encoding="utf-8", newline="\n")
    _git(directory, "add", "result.json")
    _git(directory, "commit", "-m", "Record synthetic issue result")
    assert not _git(directory, "remote", "-v")
    return {"branch": branch, "commit": _git(directory, "rev-parse", "HEAD"),
            "target_pr": None, "remote_count": 0}


def _case(root: Path, name: str, frozen_graph, current_graph,
          *, agent_fails: bool = False) -> dict:
    path = root / name
    path.mkdir()
    database = path / "run.sqlite3"
    runs = WorkflowRunStore(database)
    evidence = EvidenceStore(database)
    frozen = _frozen_input(frozen_graph)
    try:
        _gate(frozen, current_graph)
    except ValueError as error:
        counters = runs.counters()
        assert counters == {"runs": 0, "dispatch_attempts": 0,
                            "synthetic_dispatches": 0}
        return {"outcome": "refused", "reason": str(error),
                "dispatch_attempts": 0, "pr_candidate": None}

    snapshot_path = current_graph.save(path / "snapshots")
    loaded = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert loaded["snapshot_id"] == current_graph.snapshot_id
    input_digest = digest(json.dumps(frozen, sort_keys=True).encode("utf-8"))
    config = {"provider": "fake", "model": "none", "effort": "none",
              "skill_digest": digest(SKILL_BYTES), "turn_cap": 0,
              "grant": {"write_root": "disposable-checkout-only"}}
    trigger = {"type": "selected-issue", "work_key": WORK_KEY,
               "source_url": frozen["url"], "source_updated_at": frozen["updated_at"],
               "input_digest": input_digest,
               "graph_snapshot_id": current_graph.snapshot_id,
               "discovered_pr": "context-only", "target_pr": None}
    run = runs.reserve(graph=FLOW, component_code=COMPONENT_CODE,
                       resolved_config=config, trigger=trigger)
    invocation = "fake-agent-" + run["run_id"]
    evidence.reserve(run_id=run["run_id"], trace_id=run["trace_id"],
                     stage_id="fake-agent", invocation_id=invocation)
    binding = {"work_key": WORK_KEY, "source_url": frozen["url"],
               "source_updated_at": frozen["updated_at"],
               "input_digest": input_digest,
               "graph_snapshot_id": current_graph.snapshot_id,
               "run_id": run["run_id"], "trace_id": run["trace_id"],
               "component_revision": run["component_revisions"]["fake-agent"],
               "target_pr": None}

    def fake_agent(run_id: str) -> dict:
        runs.record_synthetic_dispatch(run_id)
        evidence.record_native_session(invocation, "synthetic-" + run_id)
        evidence.append_raw_event(
            invocation, source_event_id="fake-1", kind="message",
            payload={"summary": "fake agent received selected issue",
                     "work_key": WORK_KEY})
        if agent_fails:
            raise RuntimeError("injected_fake_agent_failure")
        candidate = _local_candidate(path / "checkout", binding)
        binding["candidate_commit"] = candidate["commit"]
        binding["candidate_branch"] = candidate["branch"]
        evidence.append_raw_event(
            invocation, source_event_id="fake-2", kind="result",
            payload={"summary": "local Git commit created",
                     "commit": candidate["commit"]})
        evidence.project_unprojected()
        evidence.mark_complete(invocation)
        return candidate

    candidate = None
    try:
        candidate = runs.dispatch(run["run_id"], fake_agent)
    except RuntimeError as error:
        if not agent_fails or str(error) != "injected_fake_agent_failure":
            raise
        evidence.sweep_crashed()
        assert not (path / "checkout").exists()
    record = runs.get(run["run_id"])
    trace = evidence.inspect()
    receipts = [row for row in trace["raw_events"]
                if row["invocation_id"] == invocation]
    projections = [row for row in trace["projections"]
                   if row["invocation_id"] == invocation]
    invocation_state = next(row for row in trace["invocations"]
                            if row["invocation_id"] == invocation)
    assert len(receipts) == len(projections)
    assert runs.counters()["dispatch_attempts"] == 1
    assert runs.counters()["synthetic_dispatches"] == 1
    if agent_fails:
        assert record["status"] == "failed" and not record["evidence_complete"]
        assert invocation_state["status"] == "crashed"
        assert invocation_state["stream_state"] == "partial"
        assert len(receipts) == 1 and candidate is None
    else:
        assert record["status"] == "completed" and record["evidence_complete"]
        assert invocation_state["status"] == "completed"
        assert invocation_state["stream_state"] == "complete"
        assert len(receipts) == 2 and candidate is not None
        assert candidate["target_pr"] is None
        assert candidate["branch"].endswith(run["run_id"])
        assert _git(path / "checkout", "rev-parse", "HEAD") == candidate["commit"]
        written = json.loads((path / "checkout" / "result.json").read_text(encoding="utf-8"))
        assert written == {key: value for key, value in binding.items()
                           if key not in {"candidate_commit", "candidate_branch"}}
    return {"outcome": record["status"], "run_id": run["run_id"],
            "trace_id": run["trace_id"], "graph_snapshot_id": current_graph.snapshot_id,
            "input_digest": input_digest, "component_revision": binding["component_revision"],
            "dispatch_attempts": record["dispatch_attempts"],
            "receipt_count": len(receipts), "projection_count": len(projections),
            "stream_state": invocation_state["stream_state"],
            "pr_candidate": candidate, "binding": binding if candidate else None}


def run_cases(root: Path) -> dict:
    pages = _pages()
    frozen_graph = _graph(pages)
    assert frozen_graph.readiness()[WORK_KEY] == "ready"
    stale = deepcopy(pages)
    stale[0]["data"]["repository"]["issues"]["nodes"][1]["body"] += " Changed."
    stale[0]["data"]["repository"]["issues"]["nodes"][1]["updatedAt"] = "2026-10-02T07:00:00Z"
    blocked = deepcopy(pages)
    blocked[0]["data"]["repository"]["issues"]["nodes"][0]["state"] = "OPEN"
    incomplete = deepcopy(pages)
    incomplete[0]["data"]["repository"]["issues"]["nodes"][1]["blockedBy"]["totalCount"] = 2
    cases = {
        "ready_success": _case(root, "ready-success", frozen_graph, _graph(pages)),
        "stale_source": _case(root, "stale-source", frozen_graph, _graph(stale)),
        "opened_prerequisite": _case(root, "opened-prerequisite", frozen_graph, _graph(blocked)),
        "incomplete_blockers": _case(root, "incomplete-blockers", frozen_graph, _graph(incomplete)),
        "fake_agent_failure": _case(root, "fake-agent-failure", frozen_graph,
                                    _graph(pages), agent_fails=True),
    }
    assert cases["ready_success"]["outcome"] == "completed"
    assert all(cases[key]["outcome"] == "refused" for key in
               ("stale_source", "opened_prerequisite", "incomplete_blockers"))
    assert cases["fake_agent_failure"]["outcome"] == "failed"
    return {"fixture_digest": digest(FIXTURE.read_bytes()),
            "skill_digest": digest(SKILL_BYTES),
            "flow_digest": digest(json.dumps(FLOW, sort_keys=True).encode("utf-8")),
            "model_turns": 0, "github_writes": 0, "cases": cases}


def main(record: bool = False) -> dict:
    with TemporaryDirectory(prefix="laomedo-exp19-") as temporary:
        observation = run_cases(Path(temporary))
    if record:
        output = Path(__file__).with_name("observation.json")
        output.write_text(json.dumps(observation, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8", newline="\n")
        print(output)
    else:
        print(json.dumps(observation, indent=2, sort_keys=True))
    return observation


if __name__ == "__main__":
    if sys.argv[1:] not in ([], ["--record"]):
        raise SystemExit("usage: python -m experiments.exp19.probe [--record]")
    main(record=sys.argv[1:] == ["--record"])
