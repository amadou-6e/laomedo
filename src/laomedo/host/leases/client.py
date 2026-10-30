"""Implementation owned by host / leases / client."""

from __future__ import annotations

from pathlib import Path
from laomedo.host.leases.settings import SERVICE_STALE_SECONDS
from laomedo.host.leases.models import ContainerIdentity
from laomedo.host.leases.utils import _read_float, _read_json, _write_float, _write_json
import logging
import os
import secrets
import threading
import time
from laomedo.host.leases.models import LeaseLossObservation
from laomedo.host.leases.utils import log_heartbeat_failure


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
        docker_endpoint: str,
        accept_timeout: float = 5.0,
        mediation_request: dict | None = None,
    ):
        if not isinstance(docker_endpoint, str) or not docker_endpoint:
            raise RuntimeError("lease_service_unavailable")
        identity = ContainerIdentity(
            name=name, run_id=run_id, token=token, docker_endpoint=docker_endpoint
        )
        self.state = Path(service_state).resolve()
        info = _read_json(self.state / "service.json")
        alive = _read_float(self.state / "service.alive")
        alive_monotonic = _read_float(self.state / "service.alive.monotonic")
        now_monotonic = time.monotonic()
        if (
            info is None
            or alive is None
            or alive_monotonic is None
            or alive_monotonic > now_monotonic + 1
            or now_monotonic - alive_monotonic > SERVICE_STALE_SECONDS
            or time.time() - alive > SERVICE_STALE_SECONDS
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
        _write_float(pending / "heartbeat", time.time())
        _write_float(pending / "heartbeat.monotonic", time.monotonic())
        _write_json(
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
            accepted = _read_json(self.dir / "accepted.json")
            if accepted is not None:
                break
            refused = _read_json(self.dir / "result.json")
            if refused is None:
                refused = _read_json(self.dir / "refused.json")
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
        self.loss = None
        self.result = None

        def heartbeat() -> None:
            while not self.stop_event.wait(1):
                stage = "client_wall"
                try:
                    _write_float(self.dir / "heartbeat", time.time())
                    stage = "client_monotonic"
                    _write_float(self.dir / "heartbeat.monotonic", time.monotonic())
                except OSError as error:
                    log_heartbeat_failure(stage, error)
                self._check_service(cancelled)

        self.thread = threading.Thread(target=heartbeat, daemon=True)
        self.thread.start()

    def _check_service(self, cancelled):
        """Apply existing health comparisons; signal security before diagnostics."""
        alive_at = _read_float(self.state / "service.alive")
        alive_monotonic = _read_float(self.state / "service.alive.monotonic")
        current = _read_json(self.state / "service.json")
        now_monotonic = time.monotonic()
        reason, age = None, None
        if alive_at is None:
            reason = "wall_heartbeat_unavailable"
        elif alive_monotonic is None:
            reason = "monotonic_heartbeat_unavailable"
        elif alive_monotonic > now_monotonic + 1:
            reason, age = "monotonic_heartbeat_future", now_monotonic - alive_monotonic
        elif now_monotonic - alive_monotonic > SERVICE_STALE_SECONDS:
            reason, age = "monotonic_heartbeat_stale", now_monotonic - alive_monotonic
        elif (wall_age := time.time() - alive_at) > SERVICE_STALE_SECONDS:
            reason, age = "wall_heartbeat_stale", wall_age
        elif current is None:
            reason = "service_record_unavailable"
        elif current.get("instance") != self.instance:
            reason = "service_instance_changed"
        if reason is not None:
            first_loss = not self.lost.is_set()
            self.lost.set()
            cancelled.set()
            if first_loss:
                try:
                    self.loss = LeaseLossObservation(reason=reason, age_seconds=age)
                    _write_json(self.dir / "loss.json", self.loss.to_record())
                except Exception:
                    pass

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
            result = _read_json(self.dir / "result.json")
            if result is not None:
                self.result = result
                if (
                    self.lost.is_set()
                    or result.get("reason") != "done"
                    or result.get("cleanup_verified") is not True
                ):
                    raise RuntimeError("lease_service_unverified")
                return result
            time.sleep(0.05)
        raise RuntimeError("lease_service_unverified")
