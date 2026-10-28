"""Implementation owned by host / leases / service."""

from __future__ import annotations

import laomedo.host.leases.server as _leases_server
from pathlib import Path
import laomedo.host.leases.settings as _leases_settings
import laomedo.host.leases.grants as _leases_grants
import laomedo.host.leases.models as _leases_models
import laomedo.host.leases.utils as _leases_utils
import laomedo.host.mediation.store as _mediation_store
import logging
import os
import secrets
import threading
import time


class LeaseService:
    def __init__(
        self,
        state: Path,
        *,
        port: int = 0,
        host: str = "127.0.0.1",
        loss_seconds: float = _leases_settings.LOSS_SECONDS,
        cleanup=_leases_utils.cleanup_after_loss,
        mediator: _mediation_store.MediationStore | None = None,
        mediation_authority=None,
    ):
        self.state = state.resolve()
        (self.state / "leases").mkdir(parents=True, exist_ok=True)
        self.loss_seconds = loss_seconds
        self.cleanup = cleanup
        self.book = _leases_grants.GrantBook(self.state / "grant-events.jsonl")
        self.mediator = mediator
        self.mediation_authority = mediation_authority
        self.lease_scope = str(self.state)
        if mediator is not None:
            # An old service instance cannot continue authorizing writes after
            # restart. Its lease is not silently adopted by this instance.
            mediator.revoke_lease_scope(self.lease_scope)
        self.server = _leases_server.LeaseHTTPServer(
            self.book, mediator, None, host=host, port=port
        )
        self.instance = secrets.token_hex(8)
        self.stopping = threading.Event()
        self._finishing: set[Path] = set()
        self._finishing_lock = threading.Lock()

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def _beat(self) -> None:
        while not self.stopping.is_set():
            try:
                self._publish_heartbeat()
            except OSError:
                logging.warning("lease_service_heartbeat_write_failed")
            self.stopping.wait(1)

    def _publish_heartbeat(self) -> None:
        _leases_utils._write_float(self.state / "service.alive", time.time())
        _leases_utils._write_float(
            self.state / "service.alive.monotonic", time.monotonic()
        )

    def _accept(self, lease_dir: Path, lease: dict, now: float) -> None:
        beat = _leases_utils._read_float(lease_dir / "heartbeat")
        beat_monotonic = _leases_utils._read_float(lease_dir / "heartbeat.monotonic")
        now_monotonic = time.monotonic()
        if (
            beat is None
            or beat_monotonic is None
            or beat_monotonic > now_monotonic + 1
            or now_monotonic - beat_monotonic > self.loss_seconds
            or beat > now + 1
            or now - beat > self.loss_seconds
        ):
            raise RuntimeError("lease_heartbeat_invalid")
        expiry_cap = min(beat, now) + _leases_settings.MAX_FROM_HEARTBEAT_SECONDS
        expiry_cap_monotonic = (
            min(beat_monotonic, now_monotonic)
            + _leases_settings.MAX_FROM_HEARTBEAT_SECONDS
        )
        if self.mediator is None:
            grant_id, secret = self.book.issue(
                lease["token"], now, expiry_cap, expiry_cap_monotonic
            )
        else:
            request = lease.get("mediation")
            if not isinstance(request, dict) or not all(
                isinstance(request.get(key), str) and request[key]
                for key in ("invocation_id", "repository", "branch")
            ):
                raise RuntimeError("mediated_lease_request_invalid")
            # Lease files originate on the runner side. The service must not
            # treat its requested repo/branch/operations as authorization.
            scope = (
                self.mediation_authority(lease, request)
                if self.mediation_authority is not None
                else None
            )
            if (
                not isinstance(scope, dict)
                or any(
                    scope.get(key) != request[key]
                    for key in ("invocation_id", "repository", "branch")
                )
                or not isinstance(scope.get("operations"), set)
            ):
                raise RuntimeError("mediated_lease_not_authorized")
            grant_id, secret = self.mediator.issue(
                run_id=lease["run_id"],
                invocation_id=scope["invocation_id"],
                repository=scope["repository"],
                branch=scope["branch"],
                operations=scope["operations"],
                approval_identity=scope.get("approval_identity"),
                connection_id=scope.get("connection_id"),
                connection_generation=scope.get("connection_generation"),
                target_prs=scope.get("target_prs", {}),
                base_branch=scope.get("base_branch", "main"),
                ttl_seconds=_leases_settings.GRANT_TTL_SECONDS,
                lease_token=lease["token"],
                lease_scope=self.lease_scope,
                service_instance=self.instance,
                expires_not_after=expiry_cap,
                expires_not_after_monotonic=expiry_cap_monotonic,
            )
        try:
            # Never create a live bearer using inherited broad file modes.
            secret_path = lease_dir / "grant.secret"
            descriptor = os.open(
                secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            with os.fdopen(descriptor, "w", encoding="utf-8") as secret_file:
                secret_file.write(secret)
            _leases_utils._write_json(
                lease_dir / "accepted.json",
                {
                    "instance": self.instance,
                    "token": lease["token"],
                    "grant_id": grant_id,
                    "accepted_at": now,
                },
            )
        except Exception:
            if self.mediator is None:
                self.book.revoke(lease["token"], time.time())
            else:
                self.mediator.revoke_lease(
                    run_id=lease["run_id"],
                    lease_token=lease["token"],
                    lease_scope=self.lease_scope,
                )
            raise

    def _finish(self, lease_dir: Path, lease: dict, reason: str, now: float) -> None:
        with self._finishing_lock:
            if lease_dir in self._finishing:
                return
            self._finishing.add(lease_dir)
        try:
            self._revoke_and_cleanup(lease_dir, lease, reason, now)
        except Exception:
            with self._finishing_lock:
                self._finishing.discard(lease_dir)
            raise

    def _revoke_and_cleanup(
        self, lease_dir: Path, lease: dict, reason: str, now: float
    ) -> None:
        detected_at_monotonic = time.monotonic()
        if self.mediator is None:
            revoked = self.book.revoke(lease["token"], now)
        else:
            revoked = self.mediator.revoke_lease(
                run_id=lease["run_id"],
                lease_token=lease["token"],
                lease_scope=self.lease_scope,
            )
        revoked_at = time.time()
        revoked_at_monotonic = time.monotonic()
        # Publish the authorization boundary separately from container cleanup
        # so callers can verify denial while the old container still exists.
        _leases_utils._write_json(
            lease_dir / "revoked.json",
            {
                "reason": reason,
                "revoked_grants": revoked,
                "detected_at": now,
                "revoked_at": revoked_at,
                "detected_at_monotonic": detected_at_monotonic,
                "revoked_at_monotonic": revoked_at_monotonic,
            },
        )

        def finish_cleanup() -> None:
            try:
                if reason == "done":
                    state, _ = _leases_utils.inspect_exact(
                        _leases_models.ContainerIdentity.from_registration(lease)
                    )
                    verified, detail = state == "absent", state
                else:
                    verified, detail = self.cleanup(
                        _leases_models.ContainerIdentity.from_registration(lease)
                    )
            except Exception:
                verified, detail = False, "cleanup_error"
            try:
                _leases_utils._write_json(
                    lease_dir / "result.json",
                    {
                        "reason": reason,
                        "revoked_grants": revoked,
                        "detected_at": now,
                        "revoked_at": revoked_at,
                        "cleanup_finished_at": time.time(),
                        "detected_at_monotonic": detected_at_monotonic,
                        "revoked_at_monotonic": revoked_at_monotonic,
                        "cleanup_finished_at_monotonic": time.monotonic(),
                        "cleanup_verified": verified,
                        "state": detail,
                    },
                )
            finally:
                with self._finishing_lock:
                    self._finishing.discard(lease_dir)

        threading.Thread(
            target=finish_cleanup, daemon=True, name="laomedo-lease-cleanup"
        ).start()

    def tick(self) -> None:
        for lease_dir in sorted((self.state / "leases").iterdir()):
            if (
                not lease_dir.is_dir()
                or (lease_dir / "result.json").exists()
                or lease_dir in self._finishing
            ):
                continue
            try:
                self._tick_lease(lease_dir, time.time())
            except Exception as error:
                # One runner-controlled lease must not stop revocation and
                # exact-container cleanup for every other run.
                self._refuse_lease(lease_dir, time.time(), error)

    def _tick_lease(self, lease_dir: Path, now: float) -> None:
        lease = _leases_utils._read_json(lease_dir / "lease.json")
        if (
            lease is None
            or lease.get("token") != lease_dir.name
            or not all(
                isinstance(lease.get(k), str) and lease[k]
                for k in ("token", "run_id", "name")
            )
        ):
            raise RuntimeError("lease_identity_invalid")
        if not (lease_dir / "accepted.json").exists():
            self._accept(lease_dir, lease, now)
            return
        accepted = _leases_utils._read_json(lease_dir / "accepted.json")
        if accepted is None or accepted.get("instance") != self.instance:
            self._finish(lease_dir, lease, "service_restart", now)
            return
        if (lease_dir / "done").exists():
            self._finish(lease_dir, lease, "done", now)
            return
        beat = _leases_utils._read_float(lease_dir / "heartbeat")
        beat_monotonic = _leases_utils._read_float(lease_dir / "heartbeat.monotonic")
        now = time.time()
        now_monotonic = time.monotonic()
        if (
            beat is None
            or beat_monotonic is None
            or beat_monotonic > now_monotonic + 1
            or now_monotonic - beat_monotonic > self.loss_seconds
            or beat > now + 1
            or now - beat > self.loss_seconds
        ):
            self._finish(lease_dir, lease, "heartbeat_lost", now)
        elif self.mediator is None:
            self.book.renew(
                lease["token"],
                now,
                min(beat, now) + _leases_settings.MAX_FROM_HEARTBEAT_SECONDS,
                min(beat_monotonic, now_monotonic)
                + _leases_settings.MAX_FROM_HEARTBEAT_SECONDS,
            )
        elif not self.mediator.renew_lease(
            run_id=lease["run_id"],
            lease_token=lease["token"],
            lease_scope=self.lease_scope,
            ttl_seconds=_leases_settings.GRANT_TTL_SECONDS,
            expires_not_after=min(beat, now)
            + _leases_settings.MAX_FROM_HEARTBEAT_SECONDS,
            expires_not_after_monotonic=(
                min(beat_monotonic, now_monotonic)
                + _leases_settings.MAX_FROM_HEARTBEAT_SECONDS
            ),
        ):
            self._finish(lease_dir, lease, "grant_expired", now)

    def _refuse_lease(self, lease_dir: Path, now: float, error: Exception) -> None:
        with self._finishing_lock:
            if lease_dir in self._finishing:
                return
            self._finishing.add(lease_dir)
        lease = _leases_utils._read_json(lease_dir / "lease.json")
        valid = (
            lease is not None
            and lease.get("token") == lease_dir.name
            and all(
                isinstance(lease.get(k), str) and lease[k]
                for k in ("token", "run_id", "name")
            )
        )
        code = (
            str(error)
            if isinstance(error, RuntimeError)
            and str(error)
            in {
                "lease_identity_invalid",
                "mediated_lease_request_invalid",
                "mediated_lease_not_authorized",
            }
            else type(error).__name__
        )
        try:
            # The final result waits for exact cleanup. Give a registering
            # runner the refusal immediately, without implying cleanup has
            # finished or allowing dispatch.
            _leases_utils._write_json(
                lease_dir / "refused.json", {"error_code": code, "detected_at": now}
            )
        except OSError:
            pass
        revoked, revocation_verified = [], False
        if valid:
            try:
                revoked = (
                    self.mediator.revoke_lease(
                        run_id=lease["run_id"],
                        lease_token=lease["token"],
                        lease_scope=self.lease_scope,
                    )
                    if self.mediator is not None
                    else self.book.revoke(lease["token"], now)
                )
                revocation_verified = True
            except Exception:
                # The use-time TTL still bounds the grant if the DB is down.
                pass

        def finish_refusal() -> None:
            cleanup_verified, detail = False, "identity_invalid"
            try:
                if valid:
                    try:
                        cleanup_verified, detail = self.cleanup(
                            _leases_models.ContainerIdentity.from_registration(lease)
                        )
                    except Exception:
                        detail = "cleanup_error"
                _leases_utils._write_json(
                    lease_dir / "result.json",
                    {
                        "reason": (
                            "refused"
                            if not (lease_dir / "accepted.json").exists()
                            else "lease_error"
                        ),
                        "error_code": code,
                        "detected_at": now,
                        "revoked_grants": revoked,
                        "revocation_verified": revocation_verified,
                        "cleanup_verified": cleanup_verified,
                        "state": detail,
                    },
                )
            except OSError:
                # A broken directory may be retried, but cannot starve peers.
                pass
            finally:
                with self._finishing_lock:
                    self._finishing.discard(lease_dir)

        threading.Thread(
            target=finish_refusal, daemon=True, name="laomedo-lease-refusal"
        ).start()

    def serve(self) -> None:
        # A previous instance's publication must not become valid again when
        # this instance refreshes the heartbeat files on the same state path.
        (self.state / "service.json").unlink(missing_ok=True)
        # Refuse startup if either initial heartbeat cannot be published.
        # Clients may see service.json only after both are fresh.
        self._publish_heartbeat()
        _leases_utils._write_json(
            self.state / "service.json",
            {
                "pid": os.getpid(),
                "port": self.port,
                "instance": self.instance,
                "started_at": time.time(),
            },
        )
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        threading.Thread(target=self._beat, daemon=True).start()
        try:
            while not self.stopping.is_set():
                self.tick()
                self.stopping.wait(_leases_settings.POLL_SECONDS)
        finally:
            self.server.shutdown()
            self.server.server_close()
