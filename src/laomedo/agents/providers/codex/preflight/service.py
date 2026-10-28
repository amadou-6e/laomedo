"""Verify the local Codex image and CLI through the optional Docker runtime."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from laomedo.agents.providers.codex import settings as codex_settings
from laomedo.agents.providers.codex.preflight import settings
from laomedo.agents.providers.codex.preflight.models import DockerSelection
from laomedo.agents.runtime.errors import RunnerError

if TYPE_CHECKING:
    from py_docker import Client


class CodexPreflight:
    """Apply Codex image/version policy while py-docker owns the probe lifecycle.

    Parameters
    ----------
    state : Path
        Existing private runner state directory, outside the source workspace.
    """

    def __init__(self, state: Path) -> None:
        """Retain only the private receipt path; do not open Docker at import time."""
        self.receipt_path = state.joinpath(settings.RECEIPT_FILENAME)

    def check(self, image: str, expected_id: str) -> DockerSelection:
        """Check one pinned image and run its real CLI without login material.

        Parameters
        ----------
        image : str
            Local image tag whose immutable ID must match the host pin.
        expected_id : str
            Reviewed image ID, including an explicitly supplied trusted-host override.

        Returns
        -------
        DockerSelection
            Verified ID and private snapshot for subsequent normal-mode CLI calls.

        Raises
        ------
        RunnerError
            Existing public pin, version, unconfirmed-check or cleanup code. A
            cleanup failure takes precedence and retains its private receipt.

        Notes
        -----
        API requests are individually bounded; the 20-second stream lifetime is
        not a total preflight deadline. No credentials or volumes enter the probe.
        """
        try:
            from docker.errors import DockerException
            from py_docker import Client
            from py_docker.connection.settings import ConnectionSettings
            from py_docker.errors import (
                CleanupUnconfirmedError,
                ConnectionConfigurationError,
                DockerOperationError,
            )
            from requests.exceptions import RequestException
        except ImportError:
            logging.getLogger(__name__).warning(
                "Local Docker runtime dependencies are missing. Install Laomedo's "
                "runner extra in the Python environment used to start this runner "
                "(python -m pip install -e '.[runner]')."
            )
            raise RunnerError("runner_docker_check_unconfirmed") from None

        snapshot = ConnectionSettings.environment_snapshot(None)
        try:
            with Client(
                settings=ConnectionSettings(
                    timeout_seconds=settings.API_TIMEOUT_SECONDS
                ),
                environment=snapshot,
            ) as client:
                client.jobs.recover(self.receipt_path)
                for folder in ("runs", "catalog", "preflight"):
                    for pending in self.receipt_path.parent.joinpath(folder).glob(
                        "*/" + codex_settings.NATIVE_RECEIPT_FILENAME
                    ):
                        client.sessions.recover(pending)
                self._probe(client, image, expected_id)
                pinned = {
                    key: value
                    for key, value in snapshot.items()
                    if key.upper() not in {"DOCKER_HOST", "DOCKER_CONTEXT"}
                }
                pinned["DOCKER_HOST"] = client.connection.endpoint
                return DockerSelection(image_id=expected_id, environment=pinned)
        except RunnerError:
            raise
        except CleanupUnconfirmedError:
            raise RunnerError("container_termination_unverified") from None
        except ConnectionConfigurationError:
            logging.getLogger(__name__).warning(
                "Docker endpoint selection was rejected: use one unambiguous local "
                "DOCKER_HOST or DOCKER_CONTEXT; TLS and remote endpoints are unsupported "
                "by this local trial. No configuration values are logged."
            )
            raise RunnerError("runner_docker_check_unconfirmed") from None
        except (
            DockerOperationError,
            DockerException,
            RequestException,
            OSError,
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
        ):
            raise RunnerError("runner_docker_check_unconfirmed") from None

    def _probe(self, client: Client, image: str, expected_id: str) -> None:
        """Delegate the hardened version probe and enforce Codex output policy.

        Parameters
        ----------
        client : Client
            Scoped SDK session on the resolved host-owned Docker endpoint.
        image : str
            Local tag inspected without pulling.
        expected_id : str
            Immutable image ID used for creation after checking the tag.

        Raises
        ------
        RunnerError
            Pin/version mismatch or cleanup that could not be confirmed.
        """
        from py_docker.containers.models import ContainerSpec
        from py_docker.errors import OwnershipConflictError
        from py_docker.jobs.models import ContainerJob
        from py_docker.streams.models import StreamLimits

        try:
            client.images.resolve(image, expected_id=expected_id)
        except OwnershipConflictError:
            raise RunnerError("docker_image_digest_changed") from None

        spec = ContainerSpec(
            image=expected_id,
            name="laomedo-codex-preflight-" + uuid4().hex,
            command=["codex", "--version"],
            user="10001:10001",
        )
        result = client.jobs.run(
            ContainerJob(
                spec=spec,
                limits=StreamLimits(
                    seconds=settings.STREAM_SECONDS, max_bytes=settings.MAX_OUTPUT_BYTES
                ),
                receipt_path=self.receipt_path,
                wait_timeout_seconds=settings.WAIT_SECONDS,
            )
        )
        try:
            version = result.stdout.decode("utf-8").strip()
        except UnicodeDecodeError:
            raise RunnerError("unsupported_codex_cli_version") from None
        if result.exit_code != 0 or version != codex_settings.CLI_VERSION:
            raise RunnerError("unsupported_codex_cli_version")
