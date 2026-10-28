"""Verify the local Codex image and CLI through the optional Docker runtime."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from laomedo.agents.providers.codex import settings as codex_settings
from laomedo.agents.providers.codex.preflight import settings
from laomedo.agents.providers.codex.preflight.models import DockerSelection
from laomedo.agents.runtime.errors import RunnerError

if TYPE_CHECKING:
    from py_docker import Client
    from py_docker.containers.models import ContainerIdentity, ContainerReservation


class CodexPreflight:
    """Own a credential-free probe and its private uncertain-create receipt.

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
                self._recover(client)
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
        """Attach before starting the bounded, non-root version probe.

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
        reservation = client.containers.reserve(spec)
        self._save(reservation)
        identity = None
        try:
            identity = client.containers.create(spec, reservation)
            stdout = bytearray()
            limits = StreamLimits(
                seconds=settings.STREAM_SECONDS, max_bytes=settings.MAX_OUTPUT_BYTES
            )
            with client.execution.attach(identity, limits) as stream:
                client.containers.start(identity)
                while frame := stream.read_frame():
                    if frame.channel == "stdout":
                        stdout.extend(frame.data)
            status = client.sdk.containers.get(identity.id).wait(
                timeout=settings.WAIT_SECONDS
            )
            try:
                version = stdout.decode("utf-8").strip()
            except UnicodeDecodeError:
                raise RunnerError("unsupported_codex_cli_version") from None
            if status.get("StatusCode") != 0 or version != codex_settings.CLI_VERSION:
                raise RunnerError("unsupported_codex_cli_version")
        finally:
            self._cleanup(client, reservation, identity)

    def _save(self, reservation: ContainerReservation) -> None:
        """Persist ownership before create without logging private label values.

        Parameters
        ----------
        reservation : ContainerReservation
            Canonical library ownership intent for uncertain-outcome recovery.
        """
        value = {
            "name": reservation.name,
            "labels": {
                key: token.get_secret_value()
                for key, token in reservation.labels.items()
            },
        }
        descriptor = os.open(
            self.receipt_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
        )
        with os.fdopen(descriptor, "w", encoding="utf-8") as target:
            json.dump(value, target)

    def _recover(self, client: Client) -> None:
        """Reconcile a retained receipt before allowing a new probe.

        Parameters
        ----------
        client : Client
            Scoped session used to inspect the prior exact reservation.

        Raises
        ------
        RunnerError
            The private receipt is corrupt or its creation/cleanup remains unknown.
        """
        from py_docker.containers.models import ContainerReservation

        if not self.receipt_path.exists():
            return
        try:
            receipt = ContainerReservation.model_validate_json(
                self.receipt_path.read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            raise RunnerError("container_termination_unverified") from None
        self._cleanup(client, receipt, None)

    def _cleanup(
        self,
        client: Client,
        reservation: ContainerReservation,
        identity: ContainerIdentity | None,
    ) -> None:
        """Remove an observed owned ID; retain intent when creation is uncertain.

        Parameters
        ----------
        client : Client
            Scoped session on the original selected endpoint.
        reservation : ContainerReservation
            Private pre-create intent, retained if reconciliation cannot finish.
        identity : ContainerIdentity or None
            Observed immutable ID, or None after an uncertain create.

        Raises
        ------
        RunnerError
            Cleanup is unconfirmed. Immediate absence after an uncertain create
            cannot prove that a delayed daemon request will not create it later.
        """
        try:
            owned = (
                identity
                if identity is not None
                else client.containers.reconcile(reservation)
            )
            if owned is None:
                raise RunnerError("container_termination_unverified")
            client.containers.remove(owned, force=True)
            self.receipt_path.unlink()
        except Exception:  # noqa: BLE001 - Any cleanup fault must retain the receipt and fail closed.
            raise RunnerError("container_termination_unverified") from None
