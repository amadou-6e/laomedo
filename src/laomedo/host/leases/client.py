"""Implementation owned by host / leases / client."""

from __future__ import annotations

from pathlib import Path
import laomedo.host.leases.settings as _leases_settings
import laomedo.host.leases.models as _leases_models
import laomedo.host.leases.utils as _leases_utils
import logging
import os
import secrets
import threading
import time


class LeaseClient:
    """Runner-side registration and heartbeat for one exact container lease."""

    def __init__(
        self,
        service_state: Path,
        *,
        run_id: str,
        name: str,
        token: str,
        cancelled: threading.Event,
        docker_endpoint: str | None = None,
        accept_timeout: float = 5.0,
        mediation_request: dict | None = None,
    ):
        if docker_endpoint is None:
            from py_docker import Client

            with Client() as docker:
                docker_endpoint = docker.connection.endpoint
        identity = _leases_models.ContainerIdentity(
            name=name, run_id=run_id, token=token, docker_endpoint=docker_endpoint
        )
        self.state = Path(service_state).resolve()
        info = _leases_utils._read_json(self.state / "service.json")
        alive = _leases_utils._read_float(self.state / "service.alive")
        alive_monotonic = _leases_utils._read_float(
            self.state / "service.alive.monotonic"
        )
        now_monotonic = time.monotonic()
        if (
            info is None
            or alive is None
            or alive_monotonic is None
            or alive_monotonic > now_monotonic + 1
            or now_monotonic - alive_monotonic > _leases_settings.SERVICE_STALE_SECONDS
            or time.time() - alive > _leases_settings.SERVICE_STALE_SECONDS
            or info.get("pid") == os.getpid()
        ):
            raise RuntimeError("lease_service_unavailable")
        self.instance = info.get("instance")
        self.port = info.get("port")
        self.dir = self.state / "leases" / token
        # The service scans only leases/. Publish the complete registration in
        # one directory rename so it cannot mistake a half-written lease for
        # an invalid runner request and permanently refuse it.
        staging_root = self.state / "pending-leases"
        staging_root.mkdir(parents=True, exist_ok=True)
        pending = staging_root / (token + "-" + secrets.token_hex(8))
        pending.mkdir(mode=0o700)
        self.lost = threading.Event()
        self.stop_event = threading.Event()
        _leases_utils._write_float(pending / "heartbeat", time.time())
        _leases_utils._write_float(pending / "heartbeat.monotonic", time.monotonic())
        _leases_utils._write_json(
            pending / "lease.json",
            identity.registration(
                runner_pid=os.getpid(),
                created_at=time.time(),
                mediation=mediation_request,
            ),
        )
        if self.dir.exists():
            raise FileExistsError(self.dir)
        os.rename(pending, self.dir)
        deadline = time.monotonic() + accept_timeout
        accepted = None
        while time.monotonic() < deadline:
            accepted = _leases_utils._read_json(self.dir / "accepted.json")
            if accepted is not None:
                break
            refused = _leases_utils._read_json(self.dir / "result.json")
            if refused is None:
                refused = _leases_utils._read_json(self.dir / "refused.json")
            if refused is not None:
                code = refused.get("error_code") or refused.get("reason", "unknown")
                raise RuntimeError(f"lease_service_refused:{code}")
            time.sleep(0.05)
        if (
            accepted is None
            or accepted.get("token") != token
            or accepted.get("instance") != self.instance
        ):
            raise RuntimeError("lease_service_did_not_accept")
        self.grant_id = accepted["grant_id"]

        def heartbeat() -> None:
            while not self.stop_event.wait(1):
                try:
                    _leases_utils._write_float(self.dir / "heartbeat", time.time())
                    _leases_utils._write_float(
                        self.dir / "heartbeat.monotonic", time.monotonic()
                    )
                except OSError:
                    logging.warning("lease_client_heartbeat_write_failed")
                alive_at = _leases_utils._read_float(self.state / "service.alive")
                alive_monotonic = _leases_utils._read_float(
                    self.state / "service.alive.monotonic"
                )
                current = _leases_utils._read_json(self.state / "service.json")
                now_monotonic = time.monotonic()
                if (
                    alive_at is None
                    or alive_monotonic is None
                    or alive_monotonic > now_monotonic + 1
                    or now_monotonic - alive_monotonic
                    > _leases_settings.SERVICE_STALE_SECONDS
                    or time.time() - alive_at > _leases_settings.SERVICE_STALE_SECONDS
                    or current is None
                    or current.get("instance") != self.instance
                ):
                    self.lost.set()
                    cancelled.set()

        self.thread = threading.Thread(target=heartbeat, daemon=True)
        self.thread.start()

    def grant_secret(self) -> str:
        return (self.dir / "grant.secret").read_text(encoding="utf-8")

    def stop_heartbeats(self) -> None:
        """Delegate loss cleanup to the independent owner; never signal done."""
        self.stop_event.set()
        self.thread.join(timeout=3)

    def finish(self, *, timeout: float = 15.0) -> dict:
        """Report a normal end after the runner verified its own cleanup."""
        self.stop_heartbeats()
        (self.dir / "done").write_text("done", encoding="utf-8")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = _leases_utils._read_json(self.dir / "result.json")
            if result is not None:
                if (
                    self.lost.is_set()
                    or result.get("reason") != "done"
                    or result.get("cleanup_verified") is not True
                ):
                    raise RuntimeError("lease_service_unverified")
                return result
            time.sleep(0.05)
        raise RuntimeError("lease_service_unverified")
