"""Internal native-export controls; fixtures are not live provider acceptance."""

import json
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import Mock, patch

from laomedo.activity.acp.capture import AcpCapture
from laomedo.activity.agent_activity.projection import project
from laomedo.activity.runner.feed import read_feed
from laomedo.agents.providers.opencode.history.models import (
    HistorySource,
    NativeExport,
    NativeHistory,
)
from laomedo.agents.providers.opencode.history.reader import HistoryReader


class OpenCodeHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / "store"
        self.store.mkdir()
        with closing(sqlite3.connect(self.store / "opencode.db")) as database:
            database.execute("CREATE TABLE internal_control(value TEXT)")
            database.execute(
                "INSERT INTO internal_control VALUES ('not a provider fixture')"
            )
            database.commit()
        (self.store / "auth.json").write_text("must not be copied")
        self.receipts = self.root / "receipts"
        self.receipts.mkdir()
        self.reader = HistoryReader(
            HistorySource(
                store=self.store,
                image_id="sha256:" + "a" * 64,
                endpoint="npipe:////./pipe/dockerDesktopLinuxEngine",
                receipts=self.receipts,
            ),
            self.root,
        )

    @staticmethod
    def exported(
        identity="ses_root",
        parent=None,
        message="message",
        text="actual payload",
        created=1000,
    ):
        return NativeExport(
            info={"id": identity, "parentID": parent, "time": {"created": created}},
            messages=[
                {
                    "info": {
                        "id": message,
                        "sessionID": identity,
                        "role": "assistant",
                        "parentID": "user",
                        "providerID": "test",
                        "modelID": "model",
                        "time": {"created": created, "completed": created + 10},
                        "tokens": {
                            "input": 2,
                            "output": 3,
                            "reasoning": 1,
                            "cache": {"read": 5, "write": 7},
                        },
                    },
                    "parts": [
                        {
                            "id": "part-" + message,
                            "messageID": message,
                            "sessionID": identity,
                            "type": "text",
                            "text": text,
                        }
                    ],
                }
            ],
        )

    def test_native_identity_and_part_binding_are_verified(self):
        exported = self.exported()
        exported.bind("ses_root", None)
        for identity, parent in [("ses_other", None), ("ses_root", "ses_parent")]:
            with self.assertRaises(ValueError):
                exported.bind(identity, parent)
        exported.messages[0]["parts"][0]["sessionID"] = "ses_foreign"
        with self.assertRaises(ValueError):
            exported.bind("ses_root", None)

    def test_metadata_job_is_offline_and_only_sees_a_consistent_database_copy(self):
        from py_docker.execution.models import CommandResult

        def export(job):
            spec = job.spec
            self.assertEqual(spec.image, self.reader.source.image_id)
            self.assertEqual(spec.network_mode, "none")
            self.assertEqual(spec.command[-2:], ["export", "ses_root"])
            self.assertEqual(len(spec.mounts), 1)
            copied = Path(spec.mounts[0].source)
            self.assertNotEqual(copied, self.store)
            self.assertFalse((copied / "auth.json").exists())
            with closing(sqlite3.connect(copied / "opencode.db")) as database:
                self.assertEqual(
                    database.execute("SELECT value FROM internal_control").fetchone()[
                        0
                    ],
                    "not a provider fixture",
                )
            return CommandResult(
                exit_code=0,
                stdout=self.exported().model_dump_json().encode(),
                stderr=b"",
            )

        with patch("py_docker.Client") as client:
            client.return_value.__enter__.return_value.jobs.run.side_effect = export
            history = self.reader.read("ses_root")
        self.assertEqual(set(history.sessions), {"ses_root"})
        self.assertEqual(list(self.root.glob("history-*")), [])

    def test_child_requires_both_native_task_link_and_exported_parent(self):
        parent = self.exported()
        parent.messages[0]["parts"].append(
            {
                "type": "tool",
                "tool": "task",
                "callID": "call",
                "state": {
                    "metadata": {
                        "sessionId": "ses_child",
                        "parentSessionId": "ses_root",
                    }
                },
            }
        )
        child = self.exported("ses_child", "ses_root", "child")
        with (
            patch.object(
                self.reader,
                "_export",
                side_effect=[
                    parent.model_dump_json().encode(),
                    child.model_dump_json().encode(),
                ],
            ),
            patch("py_docker.Client"),
        ):
            history = self.reader.read("ses_root")
        self.assertEqual(set(history.sessions), {"ses_root", "ses_child"})
        child.info["parentID"] = "ses_foreign"
        with (
            patch.object(
                self.reader,
                "_export",
                side_effect=[
                    parent.model_dump_json().encode(),
                    child.model_dump_json().encode(),
                ],
            ),
            patch("py_docker.Client"),
        ):
            with self.assertRaisesRegex(ValueError, "session binding"):
                self.reader.read("ses_root")

    def test_resume_does_not_retain_old_messages_or_double_count_acp_usage(self):
        old = self.exported(message="old", text="old text")
        current = self.exported(message="new", text="new text")
        current.messages.insert(0, old.messages[0])
        baseline = NativeHistory(root_id="ses_root", sessions={"ses_root": old})
        history = NativeHistory(root_id="ses_root", sessions={"ses_root": current})
        capture = AcpCapture(self.root, "host-attempt")
        capture.begin("ses_root", "new prompt")
        capture.update(
            "ses_root",
            {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "new text"},
            },
        )
        capture.finish("ses_root", "completed", {"totalTokens": 99999})
        self.reader.retain(history, baseline, capture, [])
        events = read_feed(self.root / "activity-events.jsonl")["events"]
        projected = project(
            [
                {"raw": event["event"], "received_at": event["received_at"]}
                for event in events
            ],
            root_thread="ses_root",
        )
        self.assertEqual(projected["usage"]["totalTokens"], 18)
        texts = [item["item"].get("text") for item in projected["items"]]
        self.assertEqual(texts, ["new text"])
        snapshots = [
            event["event"]
            for event in events
            if event["event"]["method"] == "opencode/messageSnapshot"
        ]
        self.assertEqual(snapshots[0]["params"]["source"], "native CLI export")
        self.assertEqual(
            [m["info"]["id"] for m in snapshots[0]["params"]["messages"]], ["new"]
        )

    def test_unknown_existing_child_baseline_does_not_become_attempt_usage(self):
        baseline = NativeHistory(
            root_id="ses_root", sessions={"ses_root": self.exported(message="old")}
        )
        current = self.exported(message="new", created=2000)
        current.messages.append(
            {
                "info": {
                    "id": "new-user",
                    "sessionID": "ses_root",
                    "role": "user",
                    "time": {"created": 2000},
                },
                "parts": [],
            }
        )
        history = NativeHistory(
            root_id="ses_root",
            sessions={
                "ses_root": current,
                "ses_child": self.exported("ses_child", "ses_root", created=500),
            },
        )
        with self.assertRaisesRegex(ValueError, "baseline is unknown"):
            history.attempt_messages("ses_child", baseline)

    def test_interrupted_export_batch_never_claims_inclusive_usage(self):
        history = NativeHistory(
            root_id="ses_root", sessions={"ses_root": self.exported()}
        )
        capture = AcpCapture(self.root, "host-attempt")
        capture.begin("ses_root", "prompt")
        capture.finish("ses_root", "completed")
        self.reader.retain(history, None, capture, [])
        events = read_feed(self.root / "activity-events.jsonl")["events"]
        interrupted = [
            event
            for event in events
            if event["event"]["method"] != "opencode/exportCompleted"
        ]
        partial = project(
            [
                {"raw": event["event"], "received_at": event["received_at"]}
                for event in interrupted
            ],
            root_thread="ses_root",
        )
        self.assertIsNone(partial["usage"])
        self.assertIsNone(partial["cost"]["amount"])

    def test_cleanup_uncertainty_preserves_private_copy_and_does_not_claim_cleanup(
        self,
    ):
        from py_docker.errors import CleanupUnconfirmedError
        from laomedo.agents.runtime.errors import RunnerError

        with patch("py_docker.Client") as client:
            client.return_value.__enter__.return_value.jobs.run.side_effect = (
                CleanupUnconfirmedError("internal cleanup control")
            )
            with self.assertRaisesRegex(
                RunnerError, "opencode_container_cleanup_unverified"
            ):
                self.reader.read("ses_root")
        self.assertEqual(len(list(self.root.glob("history-*"))), 1)
