"""Import-only loader for immutable EXP104 internal controls, never a live probe."""

import ast
import copy
import hashlib
import json
from pathlib import Path
import runpy
import sys
from types import ModuleType
from unittest.mock import patch


class RetainedNativeProbeLoader:
    """Load separately named control modules without legacy runtime facades."""

    @classmethod
    def normalize(cls, node):
        if (
            isinstance(node, ast.Name)
            and node.id == "_migrated_workspace_skills_verify"
        ):
            return ast.Attribute(
                value=ast.Name(id="workspace_skills", ctx=ast.Load()),
                attr="verify",
                ctx=node.ctx,
            )
        for field, value in ast.iter_fields(node):
            if isinstance(value, list):
                setattr(
                    node,
                    field,
                    [
                        cls.normalize(item) if isinstance(item, ast.AST) else item
                        for item in value
                        if not isinstance(item, (ast.Import, ast.ImportFrom))
                    ],
                )
            elif isinstance(value, ast.AST):
                setattr(node, field, cls.normalize(value))
        return node

    @classmethod
    def load(cls):
        root = Path(__file__).resolve().parents[1]
        record = json.loads(
            (root / "tests/contracts/agent-skill-workspace-6656c1c.json").read_text(
                encoding="utf-8"
            )
        )
        with patch.object(sys, "path", [str(root / "tools/migrations"), *sys.path]):
            migrate = runpy.run_path(
                str(root / "tools/migrations/migrate_module_paths.py")
            )["migrate_source"]
        originals = {}
        for item in record["retained_files"]:
            path = root / item["path"]
            raw = path.read_bytes()
            if hashlib.sha256(raw).hexdigest() != item["sha256"]:
                raise ValueError(
                    "Retained EXP104 source hash mismatch: " + item["path"]
                )
            originals[path.stem] = (path, raw.decode("utf-8-sig"))
        modules = {}
        for stem in ("native_localrunner_worker", "native_localrunner_probe"):
            path, original = originals[stem]
            migrated = migrate(original)
            if stem == "native_localrunner_probe":
                migrated = migrated.replace(
                    "from experiments.exp104.native_localrunner_worker import ",
                    "from _retained_exp104_worker_control import ",
                )
            before = cls.normalize(copy.deepcopy(ast.parse(original)))
            after = cls.normalize(ast.parse(migrated))
            if ast.dump(before) != ast.dump(after):
                raise ValueError(
                    "Retained EXP104 control changed beyond imports/symbol qualification"
                )
            name = (
                "_retained_exp104_worker_control"
                if stem.endswith("worker")
                else "_retained_exp104_probe_control"
            )
            if name in sys.modules:
                raise ValueError("Retained EXP104 control module is already in use")
            module = ModuleType(name)
            # Preserve original resource resolution; __main__ remains unselected.
            module.__file__ = str(path)
            modules[stem] = module
            if stem.endswith("worker"):
                exec(compile(migrated, str(path), "exec"), module.__dict__)
            else:
                temporary_name = "_retained_exp104_worker_control"
                temporary_worker = modules["native_localrunner_worker"]
                if temporary_name in sys.modules:
                    raise ValueError("Retained EXP104 worker module is already in use")
                sys.modules[temporary_name] = temporary_worker
                try:
                    exec(compile(migrated, str(path), "exec"), module.__dict__)
                finally:
                    if sys.modules.get(temporary_name) is not temporary_worker:
                        raise ValueError(
                            "Retained EXP104 worker module ownership changed"
                        )
                    del sys.modules[temporary_name]
        return modules["native_localrunner_worker"], modules["native_localrunner_probe"]
