"""Credential-free EXP-08 invariants for both byte representations."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from experiments.exp08.probe import run_case


class SkillMaterializationTests(unittest.TestCase):
    def test_lf_and_crlf_are_distinct_exact_revisions_and_stay_isolated(self):
        with TemporaryDirectory(prefix="laomedo-exp08-test-") as temp:
            root = Path(temp)
            lf = run_case(b"\n", root / "lf")
            crlf = run_case(b"\r\n", root / "crlf")
        self.assertNotEqual(lf["source_file_sha256"], crlf["source_file_sha256"])
        self.assertNotEqual(lf["source_tree_hash"], crlf["source_tree_hash"])
        for result in (lf, crlf):
            self.assertEqual(result["source_tree_hash"], result["effective_skill_hash"])
            self.assertEqual(result["source_tree_hash"], result["source_hash_after_edit"])
            self.assertEqual(result["source_tree_hash"], result["stored_hash_after_edit"])
            self.assertNotEqual(result["effective_skill_hash"], result["post_edit_skill_hash"])
            self.assertNotEqual(result["effective_workspace_hash"],
                                result["post_run_workspace_hash"])
            self.assertTrue(result["path_escape_rejected"])
            self.assertTrue(result["unsafe_id_rejected"])
            self.assertTrue(result["tampered_revision_refused_before_materialization"])
            self.assertEqual(result["use_evidence"], "offered")
            self.assertEqual(result["native_discovery"], "unverified; no model call")
            for field in ("git_status_before", "git_status_after_materialization",
                          "git_status_after_edit", "git_status_after_cleanup"):
                self.assertEqual(result[field], "")


if __name__ == "__main__":
    unittest.main()
