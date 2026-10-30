"""Run retained EXP-08 internal controls from explicit import-only temporary copies.

The original probe, assertions and observations remain unchanged. This is an
internal filesystem/Git control, never a real Agent or browser acceptance result.
"""

import argparse
import ast
import hashlib
import json
from pathlib import Path
import runpy
import sys
import tempfile
import unittest


def verify_import_only(before: str, after: str) -> None:
    trees = [ast.parse(before), ast.parse(after)]
    for tree in trees:
        tree.body = [
            node
            for node in tree.body
            if not isinstance(node, (ast.Import, ast.ImportFrom))
        ]
    if ast.dump(trees[0]) != ast.dump(trees[1]):
        raise ValueError("Retained EXP-08 migration changed more than imports")


def run_control(mode: str) -> bool:
    root = Path(__file__).resolve().parents[1]
    manifest = json.loads(
        Path(root, "tools/migrations/retained-registry-callers.json").read_text()
    )
    originals = {}
    for item in manifest["files"]:
        raw = Path(root, item["path"]).read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["sha256"]:
            raise ValueError("Retained EXP-08 source hash mismatch: " + item["path"])
        originals[Path(item["path"]).name] = raw.decode("utf-8")
    old_path, old_argv = sys.path[:], sys.argv[:]
    try:
        sys.path[:0] = [
            str(Path(root, "tools/migrations")),
            str(Path(root, "src")),
            str(root),
        ]
        migration = runpy.run_path(
            str(Path(root, "tools/migrations/migrate_module_paths.py"))
        )
        probe = migration["migrate_source"](originals["probe.py"])
        verify_import_only(originals["probe.py"], probe)
        old_import = "from experiments.exp08.probe import run_case"
        if originals["test_probe.py"].count(old_import) != 1:
            raise ValueError("Retained EXP-08 test import is ambiguous")
        tests = originals["test_probe.py"].replace(
            old_import, "from retained_exp08.probe import run_case"
        )
        verify_import_only(originals["test_probe.py"], tests)
        with tempfile.TemporaryDirectory(prefix="laomedo-retained-exp08-") as directory:
            package = Path(directory, "retained_exp08")
            package.mkdir()
            Path(package, "__init__.py").write_text("", encoding="utf-8")
            Path(package, "probe.py").write_text(probe, encoding="utf-8", newline="\n")
            Path(package, "test_probe.py").write_text(
                tests, encoding="utf-8", newline="\n"
            )
            sys.path.insert(0, directory)
            if mode == "test":
                suite = unittest.defaultTestLoader.loadTestsFromName(
                    "retained_exp08.test_probe"
                )
                return unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful()
            sys.argv = [str(Path(package, "probe.py"))]
            runpy.run_module("retained_exp08.probe", run_name="__main__")
            return True
    finally:
        sys.path[:] = old_path
        sys.argv[:] = old_argv
        for name in tuple(sys.modules):
            if name == "retained_exp08" or name.startswith("retained_exp08."):
                del sys.modules[name]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("test", "probe"))
    raise SystemExit(not run_control(parser.parse_args().mode))


if __name__ == "__main__":
    main()
