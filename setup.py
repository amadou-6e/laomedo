"""Package the canonical registered Docker inputs without maintaining copies."""

import json
import shutil
from setuptools import setup
from pathlib import Path

from setuptools.command.build_py import build_py


class DockerBuildPy(build_py):
    """Include manifest-declared inputs in wheels built from checkout or sdist."""

    def run(self):
        build_root = Path(self.build_lib).resolve()
        package = build_root / "laomedo"
        package.resolve().relative_to(build_root)
        source = (Path(__file__).resolve().parent / "src/laomedo").resolve()
        if package == source or package in source.parents or source in package.parents:
            raise ValueError("build_output_overlaps_source")
        if package.exists():
            shutil.rmtree(package)
        super().run()
        root = Path(__file__).resolve().parent / "docker"
        destination = Path(self.build_lib) / "laomedo/container_images/resources"
        destination.resolve().relative_to(build_root)
        if destination.exists():
            shutil.rmtree(destination)
        manifest = json.loads((root / "images.json").read_text(encoding="utf-8"))
        self.mkpath(str(destination))
        self.copy_file(str(root / "images.json"), str(destination / "images.json"))
        for registration in manifest.values():
            for name in registration["files"]:
                relative = Path(registration["context"]) / name
                if relative.is_absolute() or ".." in relative.parts:
                    raise ValueError("registered_build_input_outside_context")
                source = root / relative
                source.resolve().relative_to(root.resolve())
                if source.is_symlink():
                    raise ValueError("symlink_build_input")
                target = destination / relative
                target.resolve().relative_to(destination.resolve())
                self.mkpath(str(target.parent))
                self.copy_file(str(source), str(target))


setup(cmdclass={"build_py": DockerBuildPy})
