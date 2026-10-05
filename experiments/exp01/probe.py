"""Compare an installed Laomedo wheel with EXP-01's frozen response oracle."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

from laomedo.work_graph.github import import_pages
from laomedo.work_graph.model import GraphSnapshot


HERE = Path(__file__).resolve().parent
REPOSITORY = "verify/exp01"
FETCHED_AT = "2026-10-05T00:00:00+00:00"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def outside_git(path):
    for parent in (path, *path.parents):
        if (parent / ".git").exists():
            raise ValueError("Output directory must be outside a Git working tree")


def source_nodes(pages):
    return {"github:" + node["id"]: node
            for page in pages
            for node in (((page.get("data") or {}).get("repository") or {})
                         .get("issues") or {}).get("nodes", ())
            if node is not None}


def observe(snapshot, pages):
    readiness = snapshot.readiness()
    nodes = source_nodes(pages)
    integrity = all(
        item.key in nodes
        and item.repository == REPOSITORY
        and item.number == nodes[item.key]["number"]
        and item.url == nodes[item.key]["url"]
        and item.body == nodes[item.key]["body"]
        and item.updated_at == nodes[item.key]["updatedAt"]
        and item.labels == tuple(sorted(label["name"] for label in nodes[item.key]["labels"]["nodes"]))
        for item in snapshot.items
    )
    edges = sorted([
        edge.prerequisite, edge.dependent,
        edge.prerequisite_repository, edge.dependent_repository
    ] for edge in snapshot.dependencies)
    return {
        "complete": snapshot.source_complete,
        "warnings": list(snapshot.source_warnings),
        "items": {item.key: [item.number, item.state, readiness[item.key]]
                  for item in snapshot.items},
        "edges": edges,
        "source_fields_preserved": integrity,
        "native_provenance_only": all(edge.provenance == "github-native-blocker"
                                      for edge in snapshot.dependencies),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    outside_git(output)
    output.mkdir(parents=True, exist_ok=True)
    corpus_path, oracle_path = HERE / "corpus.json", HERE / "oracle.json"
    corpus = json.loads(corpus_path.read_text(encoding="utf-8"))
    oracle = json.loads(oracle_path.read_text(encoding="utf-8"))
    if set(corpus) != set(oracle):
        raise ValueError("Corpus and oracle cases differ")
    cases = {}
    snapshots = {}
    for name, pages in corpus.items():
        try:
            snapshot = import_pages(REPOSITORY, pages, FETCHED_AT)
            actual = observe(snapshot, pages)
            expected = dict(oracle[name])
            projection = expected.pop("open_focus", None)
            if projection is not None:
                filtered = snapshot.project("open", ("focus",))
                actual["open_focus"] = {
                    "items": {item["key"]: item["readiness"]
                              for item in filtered["items"]},
                    "edges": sorted([edge["prerequisite"], edge["dependent"]]
                                    for edge in filtered["dependencies"]),
                    "context_edges": sorted([edge["prerequisite"], edge["dependent"]]
                                            for edge in filtered["context_dependencies"]),
                }
                expected["open_focus"] = projection
            expected["source_fields_preserved"] = True
            expected["native_provenance_only"] = True
            passed = actual == expected
            cases[name] = {"passed": passed, "actual": actual, "expected": expected,
                           "response_sha256": sha256(json.dumps(pages, sort_keys=True,
                               separators=(",", ":"), ensure_ascii=False).encode("utf-8")).hexdigest(),
                           "snapshot_id": snapshot.snapshot_id}
            snapshots[name] = snapshot
        except Exception as error:
            cases[name] = {"passed": False, "exception": type(error).__name__,
                           "message": str(error)}

    refresh = {"passed": False}
    if "refresh_before" in snapshots and "refresh_after" in snapshots:
        before = snapshots["refresh_before"]
        after = snapshots["refresh_after"]
        path_before = before.save(output / "snapshots")
        path_after = after.save(output / "snapshots")
        retained = (path_before != path_after and path_before.exists() and path_after.exists()
                    and GraphSnapshot.from_dict(json.loads(path_before.read_text(encoding="utf-8"))).snapshot_id == before.snapshot_id
                    and GraphSnapshot.from_dict(json.loads(path_after.read_text(encoding="utf-8"))).snapshot_id == after.snapshot_id)
        tampered = json.loads(path_after.read_text(encoding="utf-8"))
        tampered["items"][0]["title"] = "tampered"
        try:
            GraphSnapshot.from_dict(tampered)
            refused_tamper = False
        except ValueError:
            refused_tamper = True
        refresh = {"passed": retained and refused_tamper,
                   "retained": retained, "tamper_rejected": refused_tamper,
                   "before": before.snapshot_id, "after": after.snapshot_id}

    import laomedo
    report = {"corpus_sha256": digest(corpus_path), "oracle_sha256": digest(oracle_path),
              "installed_package_path": str(Path(laomedo.__file__).resolve()),
              "connector_version": next(iter(snapshots.values())).connector_version if snapshots else None,
              "schema_version": next(iter(snapshots.values())).schema_version if snapshots else None,
              "cases": cases, "refresh": refresh}
    report["passed"] = all(case["passed"] for case in cases.values()) and refresh["passed"]
    result = output / "result.json"
    result.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"passed": report["passed"],
                      "cases": {name: case["passed"] for name, case in cases.items()},
                      "refresh": refresh["passed"], "result": str(result)}))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
