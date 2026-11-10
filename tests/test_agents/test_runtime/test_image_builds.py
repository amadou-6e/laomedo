"""Registered-image acquisition controls, independent of provider fixtures."""

import json
from pathlib import Path
import sys
import tempfile
import threading
import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from laomedo.container_images.errors import ImageBuildError
from laomedo.container_images.models import ImageRecipe, ImageRegistration
from laomedo.container_images.registry import ImageRegistry
from laomedo.docker import DockerRuntime


class ImageBuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / "context").mkdir()
        (root / "context/Dockerfile").write_text("FROM scratch\n")
        (root / "context/secret.env").write_text("excluded private input")
        registration = ImageRegistration(
            image="laomedo-build-test:" + root.name.lower().replace("_", "-"),
            context="context",
            files=["Dockerfile"],
            verify_command=["tool", "--version"],
            verify_output="tool 1.0",
        )
        (root / "images.json").write_text(
            json.dumps({"test": registration.model_dump()})
        )
        self.registry = ImageRegistry(root)
        self.recipe = self.registry.find(registration.image, max_bytes=4096)
        self.reference = registration.image
        self.client = Mock()
        self.client.connection.endpoint = "unix:///isolated-test.sock"
        self.image = Mock(
            id="sha256:" + "a" * 64,
            labels={"laomedo.image.recipe": self.recipe.fingerprint},
        )
        self.published = {}
        self.client.sdk.images.get.side_effect = self.lookup
        self.image.tag.side_effect = self.tag
        self.client.jobs.run.return_value = SimpleNamespace(
            exit_code=0, stdout=b"tool 1.0\n"
        )
        self.addCleanup(patch.stopall)
        patch("laomedo.docker.ImageRegistry.load", return_value=self.registry).start()

    def lookup(self, reference):
        from docker.errors import ImageNotFound

        if reference.startswith("laomedo-build:"):
            return self.image
        if reference in self.published:
            return self.published[reference]
        raise ImageNotFound("not found")

    def tag(self, repository, *, tag):
        self.published[repository + ":" + tag] = self.image
        return True

    def test_missing_image_is_built_verified_and_pinned_on_the_selected_daemon(self):
        with patch.object(DockerRuntime, "_run_build") as build:
            actual = DockerRuntime.ensure_image(self.client, self.reference)
        self.assertEqual(actual, self.image.id)
        command = build.call_args.args[0]
        self.assertEqual(command[1:3], ["--host", self.client.connection.endpoint])
        self.assertIn("laomedo.image.recipe=" + self.recipe.fingerprint, command)
        self.assertEqual(
            self.client.jobs.run.call_args.args[0].spec.image, self.image.id
        )
        self.assertEqual(self.published[self.reference], self.image)
        self.client.sdk.images.remove.assert_called_once()

    def test_existing_verified_image_is_reused_without_build_or_probe(self):
        self.published[self.reference] = self.image
        with patch.object(DockerRuntime, "_run_build") as build:
            self.assertEqual(
                DockerRuntime.ensure_image(self.client, self.reference), self.image.id
            )
        build.assert_not_called()
        self.client.jobs.run.assert_not_called()

    def test_daemon_error_is_not_classified_as_missing(self):
        from docker.errors import APIError
        from py_docker.errors import ImageResolutionError

        self.client.sdk.images.get.side_effect = APIError("private daemon diagnostic")
        with patch.object(DockerRuntime, "_run_build") as build:
            with self.assertRaises(ImageResolutionError):
                DockerRuntime.ensure_image(self.client, self.reference)
        build.assert_not_called()

    def test_stale_present_image_is_not_overwritten(self):
        self.published[self.reference] = self.image
        self.image.labels = {}
        with patch.object(DockerRuntime, "_run_build") as build:
            with self.assertRaises(ImageBuildError):
                DockerRuntime.ensure_image(self.client, self.reference)
        build.assert_not_called()
        self.image.tag.assert_not_called()

    def test_wrong_version_never_publishes_the_final_tag(self):
        self.client.jobs.run.return_value.stdout = b"tool wrong-version"
        with patch.object(DockerRuntime, "_run_build"):
            with self.assertRaises(ImageBuildError):
                DockerRuntime.ensure_image(self.client, self.reference)
        self.assertNotIn(self.reference, self.published)

    def test_explicit_pin_mismatch_is_never_weakened(self):
        from py_docker.errors import OwnershipConflictError

        self.client.images.resolve.side_effect = OwnershipConflictError("pin mismatch")
        with patch.object(DockerRuntime, "_run_build") as build:
            with self.assertRaises(OwnershipConflictError):
                DockerRuntime.ensure_image(
                    self.client, self.reference, expected_id="sha256:" + "b" * 64
                )
        build.assert_not_called()

    def test_recipe_snapshot_does_not_copy_unregistered_or_changed_inputs(self):
        root = Path(self.temp.name)
        (root / "context/Dockerfile").write_text("changed after snapshot")
        output = root / "captured"
        self.recipe.write_context(output)
        self.assertEqual((output / "Dockerfile").read_text(), "FROM scratch\n")
        self.assertFalse((output / "secret.env").exists())
        fresh = self.registry.find(self.reference, max_bytes=4096)
        self.assertNotEqual(self.recipe.fingerprint, fresh.fingerprint)

    def test_context_size_is_bounded_before_reading_a_large_file(self):
        with self.assertRaises(ImageBuildError):
            self.registry.find(self.reference, max_bytes=1)

    def test_cancelled_build_never_starts_a_process(self):
        cancelled = threading.Event()
        cancelled.set()
        with patch("laomedo.docker.subprocess.Popen") as launch:
            with self.assertRaises(ImageBuildError):
                DockerRuntime._run_build(
                    ["unused"], "test", time.monotonic() + 3, cancelled
                )
        launch.assert_not_called()

    def test_build_timeout_terminates_the_owned_process(self):
        started = time.monotonic()
        with self.assertRaises(ImageBuildError) as caught:
            DockerRuntime._run_build(
                [sys.executable, "-c", "import time;time.sleep(30)"],
                "test",
                started + 0.3,
                None,
            )
        self.assertEqual(caught.exception.phase, "image_build_timeout")
        self.assertLess(time.monotonic() - started, 5)
