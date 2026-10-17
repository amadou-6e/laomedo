import json
import os
from pathlib import Path
import tempfile
import unittest

from laomedo.skill_inspection import inspect_skill, InspectionError, MAX_FILE_BYTES
from laomedo.skill_store import SkillStore


class SkillInspectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = self.root / "source"
        source.mkdir()
        (source / "SKILL.md").write_text("---\nname: sample\n---\n# Sample\ncafé\n", encoding="utf-8")
        (source / "references").mkdir()
        (source / "references/example.md").write_text("Example", encoding="utf-8")
        (source / "scripts").mkdir()
        (source / "scripts/example.py").write_text("raise RuntimeError('never execute')", encoding="utf-8")
        (source / "asset.bin").write_bytes(b"\0\xff")
        self.store = SkillStore(self.root / "registry")
        self.record = self.store.import_skill("sample", source)
        self.revision = self.record["revision_id"]
        self.bundle = self.store._revision_dir("sample", self.revision) / "bundle"

    def read(self):
        return inspect_skill(self.store.root, "sample", self.revision)

    def test_exact_files_binary_and_unicode_without_writes(self):
        before = {p.relative_to(self.root): p.stat().st_mtime_ns for p in self.root.rglob("*")}
        result = self.read()
        self.assertEqual(result["tree_hash"], self.revision)
        files = {f["path"]: f for f in result["files"]}
        self.assertIn("café", files["SKILL.md"]["text"])
        self.assertEqual(files["asset.bin"]["kind"], "binary")
        self.assertIsNone(files["asset.bin"]["text"])
        self.assertEqual(files["references/example.md"]["file_hash"], self.record["file_hashes"]["references/example.md"])
        self.assertEqual(before, {p.relative_to(self.root): p.stat().st_mtime_ns for p in self.root.rglob("*")})

    def test_verified_raster_images_are_inlined_but_other_binary_files_are_not(self):
        import base64
        source = self.root / "source"
        image = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aT1kAAAAASUVORK5CYII=")
        (source / "pixel.png").write_bytes(image)
        (source / "diagram.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>Flow</text></svg>')
        record = self.store.import_skill("media", source)
        default = inspect_skill(self.store.root, "media", record["revision_id"])
        self.assertTrue(all("image_data_url" not in file for file in default["files"]))
        result = inspect_skill(self.store.root, "media", record["revision_id"], include_images=True)
        files = {file["path"]: file for file in result["files"]}
        self.assertEqual(files["pixel.png"]["image_data_url"], "data:image/png;base64," + base64.b64encode(image).decode())
        self.assertNotIn("image_data_url", files["asset.bin"])
        self.assertNotIn("image_data_url", files["diagram.svg"])
        (self.store._revision_dir("media", record["revision_id"]) / "bundle/pixel.png").write_bytes(b"tampered")
        with self.assertRaisesRegex(InspectionError, "skill_revision_unavailable"):
            inspect_skill(self.store.root, "media", record["revision_id"])

    def test_no_latest_or_path_selection(self):
        for skill, revision in (("../secret", self.revision), ("sample", "latest"), ("sample", "../../secret")):
            with self.subTest(skill=skill, revision=revision), self.assertRaises(InspectionError):
                inspect_skill(self.store.root, skill, revision)

    def test_missing_and_tampered_revision_fail_closed(self):
        with self.assertRaisesRegex(InspectionError, "skill_revision_unavailable"):
            inspect_skill(self.store.root, "absent", self.revision)
        (self.bundle / "SKILL.md").write_text("tampered")
        with self.assertRaisesRegex(InspectionError, "skill_revision_unavailable"):
            self.read()

    def test_symlink_never_exposes_external_contents(self):
        outside = self.root / "personal-token"
        outside.write_text("SECRET-MUST-NOT-RETURN")
        target = self.bundle / "references/example.md"
        target.unlink()
        try:
            target.symlink_to(outside)
        except OSError:
            self.skipTest("OS does not permit unprivileged symlinks")
        with self.assertRaisesRegex(InspectionError, "skill_revision_unsafe"):
            self.read()

    def test_hardlink_and_oversized_file_are_refused_before_read(self):
        target = self.bundle / "references/example.md"
        target.unlink()
        os.link(self.root / "source/SKILL.md", target)
        with self.assertRaisesRegex(InspectionError, "skill_revision_unsafe"):
            self.read()
        target.unlink()
        target.write_bytes(b"x" * (MAX_FILE_BYTES + 1))
        with self.assertRaisesRegex(InspectionError, "skill_revision_too_large"):
            self.read()

    def test_record_link_is_refused(self):
        record = self.bundle.parent / "record.json"
        outside = self.root / "record-secret"
        outside.write_text(json.dumps({"secret": "SECRET"}))
        record.unlink()
        try:
            record.symlink_to(outside)
        except OSError:
            self.skipTest("OS does not permit unprivileged symlinks")
        with self.assertRaisesRegex(InspectionError, "skill_revision_unsafe"):
            self.read()

    def test_invalid_record_and_excess_file_count_are_refused(self):
        record = self.bundle.parent / "record.json"
        original = record.read_bytes()
        record.write_text("[]")
        with self.assertRaisesRegex(InspectionError, "skill_revision_unavailable"):
            self.read()
        record.write_bytes(original)
        for index in range(125):
            (self.bundle / f"extra-{index}.txt").write_text("bounded")
        with self.assertRaisesRegex(InspectionError, "skill_revision_too_large"):
            self.read()

    def test_excess_empty_directories_are_refused(self):
        for index in range(129):
            (self.bundle / f"directory-{index}").mkdir()
        with self.assertRaisesRegex(InspectionError, "skill_revision_too_large"):
            self.read()

    def test_excess_directory_depth_is_refused(self):
        folder = self.bundle
        for index in range(17):
            folder = folder / str(index)
            folder.mkdir()
        with self.assertRaisesRegex(InspectionError, "skill_revision_too_large"):
            self.read()

    def test_no_write_api_and_authentication(self):
        try:
            from fastapi import FastAPI, Header, HTTPException
            from fastapi.testclient import TestClient
        except ImportError:
            self.skipTest("Optional FastAPI dependency checked in pinned Langflow")
        from laomedo.langflow_skill_viewer import install_routes
        app = FastAPI()
        def authenticate(authorization: str = Header(default="")):
            if authorization != "Bearer fixture":
                raise HTTPException(status_code=401)
        install_routes(app, self.store.root, authenticate)
        route = f"/api/v1/laomedo/skills/sample/{self.revision}"
        with TestClient(app) as client:
            self.assertEqual(client.get(route).status_code, 401)
            auth = {"Authorization": "Bearer fixture"}
            response = client.get(route, headers=auth)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.json(), self.read())
            self.assertEqual(client.post(route, headers=auth, json={}).status_code, 405)
            self.assertEqual(client.get("/api/v1/laomedo/skills/sample/latest", headers=auth).json()["detail"]["code"], "immutable_skill_revision_required")
            (self.bundle / "SKILL.md").write_text("corrupt")
            refused = client.get(route, headers=auth)
            self.assertEqual(refused.status_code, 404)
            self.assertNotIn(str(self.root), refused.text)
            self.assertNotIn("corrupt", refused.text)
