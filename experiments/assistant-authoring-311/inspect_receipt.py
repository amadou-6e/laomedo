"""Read only the named synthetic acceptance flow; never author or execute it."""

import json
from pathlib import Path
import sqlite3
import sys

database = Path(sys.argv[1]).resolve()
with sqlite3.connect(database.as_uri() + "?mode=ro", uri=True) as connection:
    rows = connection.execute(
        "SELECT id, name, data FROM flow WHERE name = ?",
        ("AS311 Orchard Receipt",),
    ).fetchall()
    for identifier, name, encoded in rows:
        graph = json.loads(encoded)
        nodes = []
        for node in graph.get("nodes", []):
            template = node["data"]["node"]["template"]
            nodes.append(
                {
                    "id": node["id"],
                    "type": node["data"]["type"],
                    "static_values": {
                        field: template[field].get("value")
                        for field in (
                            "input_value", "text1", "text2", "delimiter", "should_store_message"
                        )
                        if field in template
                    },
                }
            )
        edges = [
            {
                "source": edge["source"],
                "target": edge["target"],
                "output": edge["data"]["sourceHandle"]["name"],
                "input": edge["data"]["targetHandle"]["fieldName"],
            }
            for edge in graph.get("edges", [])
        ]
        print(json.dumps({"id": identifier, "name": name, "nodes": nodes, "edges": edges}))
        for receipt in connection.execute(
            "SELECT revision, diagnostics FROM laomedo_assistant_draft_receipt WHERE workflow_id = ?",
            (identifier,),
        ):
            print(json.dumps({"saved_revision": receipt[0], "diagnostics": json.loads(receipt[1])}))
        for action in connection.execute(
            "SELECT id, state, error_code, run_id FROM laomedo_assistant_graph_action WHERE workflow_id = ?",
            (identifier,),
        ):
            print(json.dumps({"action_id": action[0], "state": action[1], "result_code": action[2], "run_id": action[3]}))
            for evidence in connection.execute(
                "SELECT outputs, truncated FROM laomedo_assistant_run_evidence WHERE action_id = ? AND run_id = ?",
                (action[0], action[3]),
            ):
                print(json.dumps({"outputs": json.loads(evidence[0]), "truncated": bool(evidence[1])}))
            vertices = connection.execute(
                "SELECT id, valid FROM vertex_build WHERE flow_id = ? AND job_id = ?",
                (identifier, action[3]),
            ).fetchall()
            print(json.dumps({"exact_job_node_status": vertices}))
