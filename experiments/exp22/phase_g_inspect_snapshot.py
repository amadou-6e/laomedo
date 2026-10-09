"""Report only table/column counts for known IDs in a private Langflow snapshot."""

import argparse
import json
from pathlib import Path
import sqlite3


def quoted(identifier):
    return '"' + identifier.replace('"', '""') + '"'


def inspect(state):
    state = Path(state)
    snapshot = state / "langflow-snapshot.db"
    if not snapshot.is_file():
        raise FileNotFoundError("private_langflow_snapshot_missing")
    summary = json.loads((state / "identity-summary.json").read_text(encoding="utf-8"))
    values = {"graph_1": summary["graph_run_ids"][0],
              "graph_2": summary["graph_run_ids"][1],
              "saved_flow": summary["saved_flow_id"]}
    locations = {key: [] for key in values}
    with sqlite3.connect(snapshot.as_uri() + "?mode=ro", uri=True) as db:
        tables = [row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        for table in tables:
            columns = [row[1] for row in db.execute(f"PRAGMA table_info({quoted(table)})")]
            for column in columns:
                expression = f"instr(CAST({quoted(column)} AS TEXT), ?)"
                for key, value in values.items():
                    count = db.execute(
                        f"SELECT COUNT(*) FROM {quoted(table)} WHERE {expression} > 0",
                        (value,)).fetchone()[0]
                    if count:
                        locations[key].append({"table": table, "column": column,
                                               "matching_rows": count})
    result = {"schema_version": 1, "locations": locations,
              "limits": "substring matches, not semantic identity-column attestation"}
    (state / "identity-locations.json").write_text(json.dumps(result, indent=2),
                                                    encoding="utf-8")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(inspect(args.state)))
