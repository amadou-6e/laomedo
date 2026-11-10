"""Shared py-docker client, one-shot job and exact-receipt mechanisms."""

from collections.abc import Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
import threading
from typing import TYPE_CHECKING, Literal
import hashlib
import logging
import os
import queue
import re
import shutil
import signal
import subprocess
import tempfile
import time
from uuid import uuid4

from laomedo.container_images.errors import ImageBuildError
from laomedo.container_images.lock import ImageBuildLock
from laomedo.container_images.registry import ImageRegistry
from laomedo.container_images.settings import ImageBuildSettings

if TYPE_CHECKING:
    from py_docker import Client
    from py_docker.connection.settings import ConnectionSettings
    from py_docker.execution.models import CommandResult
    from py_docker.jobs.models import ContainerJob
    from py_docker.sessions.models import ContainerSession
    from py_docker.sessions.session import Session
    from py_docker.containers.models import ContainerIdentity
    from py_docker.containers.models import (
        ContainerReservation,
        ContainerObservation,
        CleanupResult,
    )
    from py_docker.streams.models import StreamLimits


class DockerRuntime:
    """Own self-contained client calls without provider policy or attempt state.

    Native exceptions propagate unchanged to the owning provider boundary. An
    admitted environment pins the selected endpoint; None retains native initial
    daemon discovery. No client or live session is shared between worker threads.
    """

    def __init__(
        self,
        environment: Mapping[str, str] | None,
        *,
        settings: "ConnectionSettings | None" = None,
    ):
        self._environment = dict(environment) if environment is not None else None
        self._settings = settings

    @contextmanager
    def client(self) -> Iterator["Client"]:
        """Open and close one native client, preserving native exception handling."""
        with self.connect() as client:
            yield client

    def connect(self) -> "Client":
        """Open a client whose explicit owner must close it.

        Long-lived provider scopes use this when their existing cleanup sequence
        cannot be expressed as one lexical client context. Connection selection
        is identical to client(); no provider constructs a separate SDK client.
        """
        from py_docker import Client

        options = {"environment": self._environment}
        if self._settings is not None:
            options["settings"] = self._settings
        return Client(**options)

    @classmethod
    def ensure_image(cls, client, reference, *, expected_id=None, cancelled=None):
        """Reuse or build a trusted registered image on this exact daemon.

        An explicit immutable pin is authoritative. An unregistered reference
        retains native local-only resolution. Only native ImageNotFound causes
        a build; daemon/configuration/auth failures never do. Existing images
        with stale recipe labels are refused, never overwritten automatically.
        """
        from docker.errors import DockerException, ImageNotFound
        from requests.exceptions import RequestException
        from py_docker.errors import ImageResolutionError, OwnershipConflictError

        if expected_id is not None:
            try:
                client.images.resolve(reference, expected_id=expected_id)
                return expected_id
            except ImageResolutionError:
                # The second inspection below distinguishes genuine absence.
                pass
        settings = ImageBuildSettings()
        recipe = ImageRegistry.load().find(reference, max_bytes=settings.context_bytes)
        if recipe is None:
            return client.images.resolve(reference, expected_id=expected_id)
        try:
            image = client.sdk.images.get(reference)
        except ImageNotFound:
            image = None
        except (DockerException, RequestException):
            raise ImageResolutionError("inspect local image") from None
        if image is not None:
            return cls._admit_image(image, recipe, expected_id)
        deadline = time.monotonic() + settings.build_seconds
        key = hashlib.sha256(
            (client.connection.endpoint + "\0" + reference).encode()
        ).hexdigest()
        cache = Path(tempfile.gettempdir()) / "laomedo-image-builds"
        with ImageBuildLock(
            cache / (key + ".lock"), deadline=deadline, cancelled=cancelled
        ):
            try:
                image = client.sdk.images.get(reference)
            except ImageNotFound:
                image = None
            except (DockerException, RequestException):
                raise ImageResolutionError("inspect local image") from None
            if image is not None:
                return cls._admit_image(image, recipe, expected_id)
            return cls._build_image(
                client,
                recipe,
                expected_id,
                settings,
                deadline,
                cancelled,
                cache / (key + ".json"),
            )

    @staticmethod
    def _admit_image(image, recipe, expected_id):
        from py_docker.errors import OwnershipConflictError

        if expected_id is not None:
            if image.id != expected_id:
                raise OwnershipConflictError("verify immutable image ID")
        elif (image.labels or {}).get("laomedo.image.recipe") != recipe.fingerprint:
            raise ImageBuildError("image_recipe_changed_remove_tag_to_rebuild")
        return image.id

    @classmethod
    def _build_image(
        cls, client, recipe, expected_id, settings, deadline, cancelled, receipt
    ):
        from docker.errors import DockerException, ImageNotFound
        from requests.exceptions import RequestException
        from py_docker.containers.models import ContainerSpec
        from py_docker.jobs.models import ContainerJob
        from py_docker.streams.models import StreamLimits
        from py_docker.errors import OwnershipConflictError

        registration = recipe.registration
        executable = shutil.which("docker")
        if executable is None:
            raise ImageBuildError("docker_build_cli_unavailable")
        stage = "laomedo-build:" + uuid4().hex
        logging.getLogger(__name__).warning(
            "Building missing image %s", registration.image
        )
        try:
            with tempfile.TemporaryDirectory(prefix="laomedo-image-") as directory:
                recipe.write_context(Path(directory))
                command = [
                    executable,
                    "--host",
                    client.connection.endpoint,
                    "build",
                    "--progress=plain",
                    "--file",
                    str(Path(directory) / registration.dockerfile),
                    "--tag",
                    stage,
                    "--label",
                    "laomedo.image.recipe=" + recipe.fingerprint,
                ]
                for name, value in sorted(registration.build_args.items()):
                    command.extend(["--build-arg", name + "=" + value])
                command.append(directory)
                cls._run_build(command, registration.image, deadline, cancelled)
            image = client.sdk.images.get(stage)
            if expected_id is not None and image.id != expected_id:
                raise OwnershipConflictError("verify immutable image ID")
            cls.recover_receipts(client, [receipt], kind="job")
            if cancelled is not None and cancelled.is_set():
                raise ImageBuildError("build_cancelled")
            check = cls.execute_job(
                client,
                ContainerJob(
                    spec=ContainerSpec(
                        image=image.id,
                        name="laomedo-image-check-" + uuid4().hex,
                        entrypoint=registration.verify_command[:1],
                        command=registration.verify_command[1:],
                        read_only=True,
                        network_mode="none",
                        cap_drop=["ALL"],
                    ),
                    limits=StreamLimits(
                        seconds=settings.verify_seconds, max_bytes=65536
                    ),
                    wait_timeout_seconds=settings.verify_seconds,
                    receipt_path=receipt,
                ),
                cancelled=cancelled,
            )
            if (
                check.exit_code != 0
                or check.stdout.decode("utf-8", errors="replace").strip()
                != registration.verify_output
            ):
                raise ImageBuildError("image_version_verification_failed")
            if cancelled is not None and cancelled.is_set():
                raise ImageBuildError("build_cancelled")
            # A different process not using our lock must not be silently replaced.
            try:
                client.sdk.images.get(registration.image)
            except ImageNotFound:
                pass
            else:
                raise ImageBuildError("image_appeared_during_build")
            repository, _, tag = registration.image.rpartition(":")
            if not image.tag(repository, tag=tag):
                raise ImageBuildError("image_tag_failed")
            return cls._admit_image(
                client.sdk.images.get(registration.image), recipe, expected_id
            )
        except ImageBuildError as error:
            logging.getLogger(__name__).error(
                "Image acquisition failed: %s", error.phase
            )
            raise
        except (OSError, DockerException, RequestException):
            raise ImageBuildError("image_build_failed") from None
        finally:
            try:
                client.sdk.images.remove(stage, noprune=True)
            except (DockerException, RequestException):
                # Never force removal: an uncertain verification job may retain it.
                pass

    @staticmethod
    def _read_build_output(stream, messages, stopped):
        try:
            while not stopped.is_set():
                line = stream.readline(8192)
                if not line:
                    return
                while not stopped.is_set():
                    try:
                        messages.put(line, timeout=0.1)
                        break
                    except queue.Full:
                        pass
        finally:
            while not stopped.is_set():
                try:
                    messages.put(None, timeout=0.1)
                    break
                except queue.Full:
                    pass

    @classmethod
    def _run_build(cls, command, reference, deadline, cancelled):
        """Run a bounded CLI build with no shell or request-controlled environment."""
        if cancelled is not None and cancelled.is_set():
            raise ImageBuildError("build_cancelled")
        if time.monotonic() >= deadline:
            raise ImageBuildError("image_build_timeout")
        allowed = {
            "PATH",
            "SYSTEMROOT",
            "WINDIR",
            "TEMP",
            "TMP",
            "HOME",
            "USERPROFILE",
            "DOCKER_CONFIG",
            "PROGRAMFILES",
            "PROGRAMFILES(X86)",
            "PROGRAMDATA",
            "APPDATA",
            "LOCALAPPDATA",
        }
        environment = {
            key: value for key, value in os.environ.items() if key.upper() in allowed
        }
        environment["DOCKER_BUILDKIT"] = "1"
        options = (
            {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
            if os.name == "nt"
            else {"start_new_session": True}
        )
        if os.name == "nt":
            import win32job
            import win32api

        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            **options,
        )
        job = None
        if os.name == "nt":
            try:
                job = win32job.CreateJobObject(None, "")
                limits = win32job.QueryInformationJobObject(
                    job, win32job.JobObjectExtendedLimitInformation
                )
                limits["BasicLimitInformation"][
                    "LimitFlags"
                ] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                win32job.SetInformationJobObject(
                    job, win32job.JobObjectExtendedLimitInformation, limits
                )
                win32job.AssignProcessToJobObject(job, int(process._handle))
            except BaseException:
                process.kill()
                process.wait(timeout=10)
                if job is not None:
                    win32api.CloseHandle(job)
                process.stdout.close()
                raise ImageBuildError("build_process_containment_failed") from None
        messages = queue.Queue(maxsize=128)
        stopped = threading.Event()
        reader = threading.Thread(
            target=cls._read_build_output,
            args=(process.stdout, messages, stopped),
            daemon=True,
        )
        reader.start()
        ended = False
        try:
            while process.poll() is None or not ended:
                if cancelled is not None and cancelled.is_set():
                    raise ImageBuildError("build_cancelled")
                if time.monotonic() >= deadline:
                    raise ImageBuildError("image_build_timeout")
                try:
                    line = messages.get(timeout=0.1)
                except queue.Empty:
                    continue
                if line is None:
                    ended = True
                else:
                    # Report progress without copying RUN commands or daemon diagnostics.
                    progress = re.match(r"(?:#\d+ \[[^\]]{1,80}\]|Step \d+/\d+)", line)
                    if progress:
                        logging.getLogger(__name__).info(
                            "Building %s: %s", reference, progress.group(0)
                        )
            if process.returncode:
                raise ImageBuildError("image_build_command_failed")
        finally:
            stopped.set()
            if job is not None:
                # Close kills the CLI and inherited buildx children, even after
                # its launcher exited; no PID-based global process lookup.
                win32api.CloseHandle(job)
            if process.poll() is None:
                if os.name != "nt":
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=10)
            process.stdout.close()
            reader.join(timeout=5)

    def run_job(
        self,
        job: "ContainerJob",
        *,
        cancelled: threading.Event | None = None,
        deadline: float | None = None,
        cleanup_seconds: float | None = None,
    ) -> "CommandResult":
        """Delegate exact launch, bounded output and cleanup to the native job API."""
        with self.client() as client:
            return self.execute_job(
                client,
                job,
                cancelled=cancelled,
                deadline=deadline,
                cleanup_seconds=cleanup_seconds,
            )

    @staticmethod
    def execute_job(
        client: "Client",
        job: "ContainerJob",
        *,
        cancelled: threading.Event | None = None,
        deadline: float | None = None,
        cleanup_seconds: float | None = None,
    ) -> "CommandResult":
        """Run on an explicitly borrowed client without changing its lifetime."""
        options = {}
        if cancelled is not None:
            options["cancelled"] = cancelled
        if deadline is not None:
            options["deadline"] = deadline
        if cleanup_seconds is not None:
            options["cleanup_seconds"] = cleanup_seconds
        return client.jobs.run(job, **options)

    @staticmethod
    @contextmanager
    def session(
        client: "Client",
        request: "ContainerSession",
        *,
        deadline: float | None = None,
        cleanup_seconds: float | None = None,
    ) -> Iterator["Session"]:
        """Own one interactive session on a caller-owned client.

        Enter and exit on the creator thread. Native startup, body and cleanup
        exceptions retain their identity and context-manager semantics. The
        caller closes its client after its other dependent resources; this
        scope never interprets agent readiness or a native conversation.
        """
        with DockerRuntime.start_session(
            client, request, deadline=deadline, cleanup_seconds=cleanup_seconds
        ) as session:
            yield session

    @staticmethod
    def start_session(
        client: "Client",
        request: "ContainerSession",
        *,
        deadline: float | None = None,
        cleanup_seconds: float | None = None,
    ) -> "Session":
        """Launch an explicitly owned session; its owner must call close_session.

        Use session() for lexical scope ownership. This form supports a
        persistent executor whose reader must drain at its existing close point.
        """
        options = {}
        if deadline is not None:
            options["deadline"] = deadline
        if cleanup_seconds is not None:
            options["cleanup_seconds"] = cleanup_seconds
        return client.sessions.open(request, **options)

    @staticmethod
    def run_command(
        client: "Client",
        identity: "ContainerIdentity",
        command: Sequence[str],
        limits: "StreamLimits",
    ) -> "CommandResult":
        """Execute once inside an exact owned container; never retry on failure."""
        return client.execution.run(identity, command, limits)

    @staticmethod
    def close_session(session: "Session") -> None:
        """Request exact creator-thread cleanup, retaining native cached failure.

        ACP calls this before reader disconnect to unblock its read thread. The
        enclosing session scope also exits through the same native owner; native
        Session.close preserves uncertainty rather than treating a retry as OK.
        """
        session.close()

    @staticmethod
    def inspect_reservation(
        client: "Client", reservation: "ContainerReservation"
    ) -> "ContainerObservation":
        """Inspect exact reserved ownership on the original pinned daemon."""
        return client.containers.watch(reservation).inspect()

    @staticmethod
    def cleanup_reservation(
        client: "Client", reservation: "ContainerReservation", *, watch_seconds: float
    ) -> "CleanupResult":
        """Preserve the native delayed-create watch and ownership verification."""
        return client.containers.watch(reservation).cleanup(watch_seconds=watch_seconds)

    def recover(
        self,
        receipts: Sequence[Path],
        *,
        kind: Literal["session", "job"] = "session",
    ) -> None:
        """Recover caller-selected receipts, never scan or broaden their scope."""
        if kind not in {"session", "job"}:
            raise ValueError("Unknown Docker receipt kind")
        with self.client() as client:
            self.recover_receipts(client, receipts, kind=kind)

    @staticmethod
    def recover_receipts(
        client: "Client",
        receipts: Sequence[Path],
        *,
        kind: Literal["session", "job"] = "session",
    ) -> None:
        """Recover exact receipts on a borrowed client; never broaden selection."""
        if kind not in {"session", "job"}:
            raise ValueError("Unknown Docker receipt kind")
        service = client.jobs if kind == "job" else client.sessions
        for receipt in receipts:
            service.recover(receipt)
