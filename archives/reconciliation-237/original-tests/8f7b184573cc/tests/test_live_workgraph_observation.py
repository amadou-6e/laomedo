"""Credential-free check that the recovery exporter omits private contents."""

import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from contextlib import closing
from unittest.mock import patch
from retained_github import load_retained_github

load_retained_github("experiments.exp139.runtime")
from experiments.exp139.observe_recovery import observe
from laomedo.agents.interface.output.utils import requirements


class ObservationTests(unittest.TestCase):
    def test_private_answer_and_extra_metadata_never_enter_export(self):
        private = "DUMMY_PRIVATE_TOKEN_AND_REPORT"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def save(name, value):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value))

            inputs = {
                "snapshot": {"snapshot_id": "fixture"},
                "tasks": {"failure": "fixture"},
            }
            task = json.dumps(
                {"task": "fixture", "frozen_issue": inputs["snapshot"]},
                sort_keys=True,
                ensure_ascii=False,
            )
            pinned = requirements(
                {
                    "schema_version": 1,
                    "fields": [{"name": "report", "type": "string", "required": True}],
                }
            )
            save("config.json", {"report_sha256": hashlib.sha256(b"fixed").hexdigest()})
            save(
                "activation.json", {"source_sha": "a" * 40, "manifest_sha256": "b" * 64}
            )
            save(
                "runner/turn-ledger.json",
                {"attempted_turns": 4, "max_authorized_turns": 4},
            )
            save("flow-input/inputs.json", inputs)
            save(
                "runner/runs/fixture/record.json",
                {
                    "run_id": "fixture",
                    "thread_id": "thread",
                    "input_hash": "sha256:" + hashlib.sha256(task.encode()).hexdigest(),
                    "turns": ["turn"],
                    "answer": json.dumps(
                        {"task_outcome": "failure", "report": private}
                    ),
                    "output_requirements": pinned,
                    "evidence_closure": {"reason": "closed", "private": private},
                    "precheck": {
                        "installed": True,
                        "call_count": 1,
                        "private": private,
                    },
                    "unrecognized_private_field": private,
                },
            )
            save(
                "recovery-failure.json",
                {
                    "graph_result": [
                        {
                            "outcomes": [
                                {
                                    "destination": "failure",
                                    "contract_status": "accepted",
                                }
                            ]
                        }
                    ]
                },
            )
            (root / "runner/runs/fixture/raw-events.jsonl").write_text(
                json.dumps(
                    {
                        "method": "item/tool/call",
                        "id": 1,
                        "params": {
                            "tool": "laomedo_output_precheck",
                            "threadId": "thread",
                            "namespace": None,
                            "arguments": {
                                "requirements_revision": pinned[
                                    "requirements_revision"
                                ],
                                "submission": {"report": private},
                            },
                        },
                    }
                )
                + "\n"
            )
            (root / "host").mkdir()
            (root / "host/mediator").mkdir()
            with closing(sqlite3.connect(root / "host/write-budget.sqlite")) as db, db:
                db.execute("CREATE TABLE attempts (operation TEXT)")
            with (
                closing(sqlite3.connect(root / "host/mediator/mediator.sqlite")) as db,
                db,
            ):
                db.execute("CREATE TABLE grants (revoked_at REAL)")
            with patch(
                "experiments.exp139.observe_recovery.socket.socket"
            ) as connection:
                connection.return_value.connect_ex.return_value = 1
                result = observe(root)
            self.assertNotIn(private, json.dumps(result))
            self.assertEqual(result["runs"][0]["task_outcome"], "failure")
            self.assertEqual(
                result["runs"][0]["precheck_recomputed_from_bound_calls"][0][
                    "contract_status"
                ],
                "accepted",
            )
            self.assertEqual(result["write_attempts"], [])
