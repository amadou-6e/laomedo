"""The installed Flow guard rejects old-editor autosaves after a file load."""

import inspect
from pathlib import Path
import runpy
import tempfile
from types import SimpleNamespace
import unittest

from langflow.services.database.models.flow.guards import ensure_flow_update_allowed
from tools.apply_langflow_project_storage import apply_project_storage


class StorageEditorTests(unittest.TestCase):
    def test_guard_installation_fences_old_editor_data_and_preserves_current_saves(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = (
                root
                / "src/backend/base/langflow/services/database/models/flow/guards.py"
            )
            target.parent.mkdir(parents=True)
            source = Path(inspect.getfile(ensure_flow_update_allowed)).read_text(
                encoding="utf-8"
            )
            target.write_text(source, encoding="utf-8")
            if "laomedo_storage_revision" not in source:
                apply_project_storage(root)
            installed = runpy.run_path(str(target))
            guard = installed["ensure_flow_update_allowed"]
            failure = installed["LockedFlowError"]
            flow = SimpleNamespace(
                locked=False, data={"laomedo_storage_revision": "loaded-version"}
            )
            for data in ({"nodes": []}, {"laomedo_storage_revision": "old-version"}):
                with (
                    self.subTest(data=data),
                    self.assertRaisesRegex(failure, "Reload the editor"),
                ):
                    guard(flow, {"data": data})
            guard(
                flow,
                {"data": {"laomedo_storage_revision": "loaded-version", "nodes": []}},
            )
            guard(flow, {"name": "Metadata-only update"})
            guard(SimpleNamespace(locked=False, data={}), {"data": {"nodes": []}})
