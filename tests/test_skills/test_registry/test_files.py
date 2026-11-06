"""Persisted registry bytes and invalid-record boundaries remain stable."""

from pathlib import Path
import tempfile
import unittest

from laomedo.skills.registry.errors import SkillStoreError
from laomedo.skills.registry.files import inventory, read_json, write_json
from laomedo.skills.registry.hashing import canonical_json


class RegistryFileContractTests(unittest.TestCase):
    def test_json_record_has_sorted_keys_indentation_and_one_final_newline(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            write_json(path, {"z": "é", "a": 1})
            self.assertEqual(path.read_bytes(), b'{\n  "a": 1,\n  "z": "\\u00e9"\n}\n')
            self.assertEqual(list(Path(directory).iterdir()), [path])

    def test_non_object_json_is_an_invalid_record(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            for data in (b"[]", b"null", b'"text"'):
                path.write_bytes(data)
                with (
                    self.subTest(data=data),
                    self.assertRaisesRegex(SkillStoreError, "^invalid_record$"),
                ):
                    read_json(path)

    def test_inventory_requires_the_skill_entry_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "notes.md").write_bytes(b"notes")
            with self.assertRaisesRegex(SkillStoreError, "^missing_skill_file$"):
                inventory(root)

    def test_hash_preimages_use_the_exact_escaped_canonical_bytes(self):
        self.assertEqual(canonical_json({"z": "é", "a": 1}), b'{"a":1,"z":"\\u00e9"}')
