"""Internal native-export controls; fixtures are not live provider acceptance."""

import json
from importlib.util import find_spec
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


@unittest.skipUnless(find_spec("py_docker"), "Requires optional Docker runtime")
class OpenCodeHistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / "store"
        self.store.mkdir()
        with closing(sqlite3.connect(self.store / "opencode.db")) as database:
            database.execute("CREATE TABLE internal_control(value TEXT)")
            for table in ("account", "account_state", "control_account", "credential"):
                database.execute('CREATE TABLE "' + table + '"(value TEXT)')
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

    def test_account_or_credential_rows_are_refused_before_disk_copy_or_job(self):
        for table in ("account", "account_state", "control_account", "credential"):
            with self.subTest(table=table):
                with closing(sqlite3.connect(self.store / "opencode.db")) as database:
                    database.execute('INSERT INTO "' + table + '" VALUES (?)', ("private-test-value",))
                    database.commit()
                with patch("py_docker.Client") as client:
                    with self.assertRaisesRegex(ValueError, "^opencode_history_credentials_present$"):
                        self.reader.read("ses_root")
                    client.assert_not_called()
                self.assertEqual(list(self.root.glob("history-*")), [])
                with closing(sqlite3.connect(self.store / "opencode.db")) as database:
                    database.execute('DELETE FROM "' + table + '"')
                    database.commit()

    def test_deleted_credential_page_contents_never_reach_export_copy(self):
        marker = "PRIVATE_DELETED_TEST_VALUE_" * 30
        with closing(sqlite3.connect(self.store / "opencode.db")) as database:
            database.execute("PRAGMA secure_delete=OFF")
            database.execute("INSERT INTO credential VALUES (?)", (marker,))
            database.commit()
            database.execute("DELETE FROM credential")
            database.commit()
        self.assertIn(marker.encode(), (self.store / "opencode.db").read_bytes())
        destination = self.root / "compact.db"
        self.reader._copy_database(destination)
        self.assertNotIn(marker.encode(), destination.read_bytes())

    def test_native_session_token_counters_are_not_account_credentials(self):
        with closing(sqlite3.connect(self.store / "opencode.db")) as database:
            database.execute("CREATE TABLE session(tokens_input INTEGER, tokens_output INTEGER)")
            database.execute("INSERT INTO session VALUES (10, 5)")
            database.commit()
        destination = self.root / "usage.db"
        self.reader._copy_database(destination)
        self.assertTrue(destination.is_file())

    def test_additional_api_key_bearer_and_cookie_fields_block_export(self):
        for column in ("key", "api_key", "apikey", "bearer", "cookie"):
            with self.subTest(column=column):
                with closing(sqlite3.connect(self.store / "opencode.db")) as database:
                    database.execute('CREATE TABLE external_store("' + column + '" TEXT)')
                    database.execute("INSERT INTO external_store VALUES ('private-test-value')")
                    database.commit()
                with self.assertRaisesRegex(ValueError, "opencode_history_credentials_present"):
                    self.reader._copy_database(self.root / "refused-key.db")
                self.assertFalse((self.root / "refused-key.db").exists())
                with closing(sqlite3.connect(self.store / "opencode.db")) as database:
                    database.execute("DROP TABLE external_store")
                    database.commit()

    def test_unknown_credential_schema_and_host_size_budget_fail_closed(self):
        with closing(sqlite3.connect(self.store / "opencode.db")) as database:
            database.execute("DROP TABLE credential")
            database.commit()
        with self.assertRaisesRegex(ValueError, "opencode_history_credentials_unverified"):
            self.reader._copy_database(self.root / "refused.db")
        with patch("laomedo.agents.providers.opencode.history.reader.settings.Settings") as configured:
            configured.return_value.max_database_bytes = 1
            with self.assertRaisesRegex(ValueError, "opencode_history_database_limit"):
                self.reader._copy_database(self.root / "too-large.db")

    def test_native_record_fields_use_final_message_and_actual_tool_name(self):
        first = self.exported(message="commentary", text="I will do it")
        last = self.exported(message="final", text="The actual final answer")
        last.messages[0]["parts"].append(
            {
                "type": "tool",
                "tool": "skill",
                "callID": "call-native",
                "state": {
                    "status": "completed",
                    "input": {"name": "pinned"},
                    "output": "native skill content",
                },
            }
        )
        last.messages.insert(0, first.messages[0])
        history = NativeHistory(root_id="ses_root", sessions={"ses_root": last})
        fields = history.record_fields(None)
        self.assertEqual(fields["answer"], "The actual final answer")
        self.assertEqual(fields["native_turn_id"], "final")
        self.assertEqual(fields["tools"][0]["tool"], "skill")
        self.assertEqual(fields["tools"][0]["output"], "native skill content")

    def test_unchanged_previous_child_is_excluded_from_resume_scope(self):
        old = self.exported(message="old")
        child = self.exported("ses_child", "ses_root", "child")
        previous = NativeHistory(
            root_id="ses_root", sessions={"ses_root": old, "ses_child": child}
        )
        new = self.exported(message="new")
        new.messages.insert(0, old.messages[0])
        current = NativeHistory(
            root_id="ses_root", sessions={"ses_root": new, "ses_child": child}
        )
        self.assertEqual(current.attempt_sessions(previous), {"ses_root"})
        self.assertTrue(current.terminal_complete(previous))

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

    def test_child_export_keeps_its_budget_after_slow_parent_startup(self):
        """A parent export must not reduce its child's 30s budget to five seconds."""
        parent = self.exported()
        parent.messages[0]["parts"].append({
            "type": "tool", "tool": "task", "callID": "call",
            "state": {"metadata": {"sessionId": "ses_child", "parentSessionId": "ses_root"}},
        })
        child = self.exported("ses_child", "ses_root", "child")
        calls = []

        def export(docker, private, identity, seconds):
            calls.append((identity, seconds))
            return (parent if identity == "ses_root" else child).model_dump_json().encode()

        with (
            patch.object(self.reader, "_copy_database"),
            patch.object(self.reader, "_export", side_effect=export),
            patch("py_docker.Client"),
            patch("laomedo.agents.providers.opencode.history.reader.time.monotonic", side_effect=[0, 0, 25]),
        ):
            history = self.reader.read("ses_root")
        self.assertEqual(calls, [("ses_root", 30), ("ses_child", 30)])
        self.assertEqual(set(history.sessions), {"ses_root", "ses_child"})

    def test_expired_tree_deadline_refuses_another_job_and_removes_private_copy(self):
        with (
            patch.object(self.reader, "_copy_database"),
            patch.object(self.reader, "_export") as export,
            patch("py_docker.Client"),
            patch("laomedo.agents.providers.opencode.history.reader.time.monotonic", side_effect=[0, 120]),
        ):
            with self.assertRaisesRegex(ValueError, "batch exceeded its deadline"):
                self.reader.read("ses_root")
        export.assert_not_called()
        self.assertEqual(list(self.root.glob("history-*")), [])

    def test_host_export_deadline_is_bounded_and_configurable(self):
        from laomedo.agents.providers.opencode.history.settings import Settings
        from pydantic import ValidationError

        with patch.dict("os.environ", {"LAOMEDO_OPENCODE_HISTORY_EXPORT_SECONDS": "180"}):
            self.assertEqual(Settings().export_batch_seconds, 180)
        for value in (44, 601):
            with self.subTest(seconds=value), self.assertRaises(ValidationError):
                Settings(**{"LAOMEDO_OPENCODE_HISTORY_EXPORT_SECONDS": value})
        with (
            patch.dict("os.environ", {"LAOMEDO_OPENCODE_HISTORY_EXPORT_SECONDS": "601"}),
            patch("py_docker.Client") as client,
        ):
            with self.assertRaises(ValidationError):
                self.reader.read("ses_root")
        client.assert_not_called()
        self.assertEqual(list(self.root.glob("history-*")), [])

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
