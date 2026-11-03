"""Preserve graph identity while migrating recognized source-cache revisions."""

from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
import unittest
from support.paths import repository_root
from test_shared.test_migration.utils import load_migration

migration = load_migration()
TOOL = repository_root() / "tools/migrations/migrate_module_paths.py"


class GraphRevisionTests(unittest.TestCase):
    def test_changed_code_with_a_stale_twelve_digit_revision_requires_manual_work(self):
        graph = {
            "nodes": [
                {
                    "data": {
                        "node": {
                            "metadata": {"code_hash": "0123456789ab"},
                            "template": {
                                "code": {"value": "import laomedo.local_runner\n"}
                            },
                        }
                    }
                }
            ]
        }
        source = json.dumps(graph)
        with self.assertRaisesRegex(
            migration.ManualMigrationRequired, "does not match its original source"
        ):
            migration.migrate_json_source(source)
        self.assertEqual(json.dumps(graph), source)

    def test_unchanged_code_keeps_a_stale_or_external_revision_key_byte_exact(self):
        graph = {
            "nodes": [
                {
                    "data": {
                        "node": {
                            "metadata": {"code_hash": "0123456789ab"},
                            "template": {"code": {"value": 'answer = "\u03bb"\n'}},
                        }
                    }
                }
            ]
        }
        source = json.dumps(graph, indent=2, ensure_ascii=False)
        self.assertEqual(migration.migrate_json_source(source), source)
        self.assertEqual(migration.migrate_value(graph), graph)

    def test_component_revision_hash_follows_code_without_changing_graph_identity(self):
        """Refresh the actual cache key along with imports, preserving saved user data."""
        code = "from laomedo.local_runner import LocalRunner\n"
        original_hash = sha256(code.encode()).hexdigest()[:12]
        graph = {
            "id": "saved-flow",
            "data": {
                "nodes": [
                    {
                        "id": "agent",
                        "data": {
                            "node": {
                                "metadata": {
                                    "code_hash": original_hash,
                                    "custom": "keep",
                                },
                                "template": {
                                    "code": {"value": code},
                                    "task": {"value": "laomedo.local_runner"},
                                    "run_reference_json": {
                                        "value": "existing-run-reference"
                                    },
                                },
                            }
                        },
                    }
                ],
                "edges": [],
            },
        }
        source = json.dumps(graph, indent=2)
        result = migration.migrate_json_source(source)
        updated = json.loads(result)
        definition = updated["data"]["nodes"][0]["data"]["node"]
        migrated = definition["template"]["code"]["value"]
        self.assertEqual(
            definition["metadata"]["code_hash"],
            sha256(migrated.encode()).hexdigest()[:12],
        )
        self.assertEqual(
            result,
            source.replace(json.dumps(code), json.dumps(migrated)).replace(
                original_hash, definition["metadata"]["code_hash"]
            ),
        )
        self.assertEqual(migration.migrate_value(graph), updated)
        self.assertEqual(migration.migrate_json_source(result), result)

    def test_unknown_revision_format_requires_manual_migration(self):
        """Do not assume an unknown component revision scheme is a source checksum."""
        graph = {
            "nodes": [
                {
                    "data": {
                        "node": {
                            "metadata": {"code_hash": "other-format"},
                            "template": {
                                "code": {"value": "import laomedo.local_runner\n"}
                            },
                        }
                    }
                }
            ]
        }
        with self.assertRaisesRegex(
            migration.ManualMigrationRequired, "Unknown component code hash format"
        ):
            migration.migrate_json_source(json.dumps(graph))

    def test_historical_export_path_is_refused_even_when_archived_off_branch(self):
        path = repository_root() / "examples/claude-agent/executed-flow.json"
        before = path.read_bytes() if path.exists() else None
        result = subprocess.run(
            [sys.executable, str(TOOL), "--apply", str(path)],
            capture_output=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn(b"Historical execution evidence is immutable", result.stderr)
        self.assertEqual(path.read_bytes() if path.exists() else None, before)
        self.assertFalse(
            path.with_name(path.name + ".before-module-migration").exists()
        )
