"""One native Codex sign-in for saved Agent execution and quota observations."""

import json
import logging
import threading
import time
from pathlib import Path
from uuid import uuid4
from pydantic import SecretStr
from laomedo.agents.agents.codex.models import CodexAccountIdentity, CodexLoginAttempt
from laomedo.agents.agents.codex.native import CodexNativeCredentials
from laomedo.agents.agents.codex.retained import CodexRetainedCredentials
from laomedo.agents.agents.codex.settings import (
    IMAGE,
    NATIVE_LOGIN_SECONDS,
    NATIVE_AUTH_CLEANUP_SECONDS,
)
from laomedo.agents.connections.base import BaseProviderConnection
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.models import (
    ConnectionRecord,
    ConnectionSummary,
    LoginProgress,
)
from laomedo.agents.connections.settings import MAX_CONNECTIONS
from laomedo.docker import DockerRuntime
from laomedo.host.credentials.siwc.utils import (
    _atomic_private,
    _restrict_windows_directory,
)


class CodexConnection(BaseProviderConnection):
    """Stage official-client credentials; require confirmation before replacement."""

    provider = "codex"
    cleanup_seconds = NATIVE_AUTH_CLEANUP_SECONDS
    summary_outside_lock = True

    def __init__(self, service):
        """Bind shared admission; creating this adapter never starts authentication."""
        self.service = service
        self.attempts = {}
        self.retained = CodexRetainedCredentials(service)

    def begin(self, profile_id, *, lease_hash, connection_id=None):
        """Start exactly one bounded native sign-in after explicit browser consent."""
        try:
            from py_docker.sessions.models import ContainerSession
        except ImportError:
            raise ProviderConnectionError("provider_method_unavailable") from None
        with self.service._lock:
            finished = [key for key, value in self.attempts.items() if value.settled]
            for key in finished[:-64]:
                del self.attempts[key]
            self.service.check_lease(lease_hash)
            if lease_hash in self.service.revoked_leases:
                raise ProviderConnectionError("provider_session_required")
            if self.service.login_in_progress(profile_id):
                raise ProviderConnectionError("provider_login_in_progress")
            records = self.service._records(profile_id)
            if connection_id is None and len(records) >= MAX_CONNECTIONS:
                raise ProviderConnectionError("provider_connection_limit")
            previous = (
                self.service.admitted(profile_id, connection_id)
                if connection_id
                else None
            )
            if previous and previous.provider != "codex":
                raise ProviderConnectionError("provider_method_unavailable")
            if (
                previous
                and self.service.controllers is not None
                and self.service.controllers.inventory(profile_id, connection_id)[0]
            ):
                raise ProviderConnectionError("provider_connection_busy")
            attempt_id = uuid4()
            item = CodexLoginAttempt(
                profile_id=profile_id,
                lease_hash=lease_hash,
                candidate_id=connection_id or uuid4(),
                credential_id=uuid4(),
                previous=previous,
                expires_at=time.monotonic() + NATIVE_LOGIN_SECONDS,
                progress=LoginProgress(
                    attempt_id=attempt_id, status="connecting", provider="codex"
                ),
                cancelled=threading.Event(),
                ready=threading.Event(),
                confirmation=threading.Event(),
            )
            self.attempts[attempt_id] = item
            item.worker = threading.Thread(target=self._run, args=(item,), daemon=True)
            item.worker.start()
        item.ready.wait(8)
        return self.details(profile_id, attempt_id, lease_hash=lease_hash)

    def cancel(self, profile_id, attempt_id):
        """Fence an exact attempt; the creator thread confirms native cleanup."""
        with self.service._lock:
            item = self.attempts.get(attempt_id)
            if item is None or item.profile_id != profile_id:
                raise ProviderConnectionError("provider_login_expired")
            if item.progress.status in {
                "connecting",
                "verifying",
                "awaiting_confirmation",
            }:
                item.progress.status = "cancelled"
                item.cancelled.set()
            return item.progress.model_copy()

    def has_attempt(self, attempt_id):
        """Identify a native login receipt without starting a client."""
        return attempt_id in self.attempts

    def login_in_progress(self, profile_id):
        """Preserve the original unsettled native-login guard."""
        return any(
            item.profile_id == profile_id and not item.settled
            for item in self.attempts.values()
        )

    def unsettled(self, profile_id, connection_id):
        """Keep credentials until this connection's native login worker settles."""
        return any(
            item.profile_id == profile_id
            and item.candidate_id == connection_id
            and not item.settled
            for item in self.attempts.values()
        )

    def workers(self):
        """Inventory the exact owned workers joined during service shutdown."""
        return [item.worker for item in self.attempts.values() if item.worker]

    def fence_all(self):
        """Cancel every live native attempt without releasing store ownership."""
        for item in self.attempts.values():
            item.cancelled.set()

    def cancel_profile(self, profile_id):
        """Fence pending native login for the profile that signed out."""
        for item in self.attempts.values():
            if item.profile_id == profile_id:
                self.cancel(profile_id, item.progress.attempt_id)

    def cancel_lease(self, lease_hash):
        """Fence attempts carrying this opaque revoked lease identifier."""
        for item in self.attempts.values():
            if item.lease_hash == lease_hash:
                self.cancel(item.profile_id, item.progress.attempt_id)

    def fence_connection(self, profile_id, connection_id):
        """Cancel only the disconnecting connection's pending native login."""
        for item in self.attempts.values():
            if item.profile_id == profile_id and item.candidate_id == connection_id:
                self.cancel(profile_id, item.progress.attempt_id)

    def check_attempt(self, profile_id, attempt_id, lease_hash):
        """Verify the exact owner and opaque originating lease under the service lock."""
        item = self.attempts.get(attempt_id)
        if (
            item is None
            or item.profile_id != profile_id
            or item.lease_hash != lease_hash
        ):
            raise ProviderConnectionError("provider_login_expired")

    def _root(self, profile_id, credential_id) -> Path:
        """Resolve an opaque host-owned revision below the private profile root."""
        return self.service._profile(profile_id) / str(credential_id)

    def details(self, profile_id, attempt_id, *, lease_hash):
        """Expose the device code and verified candidate only to the initiating lease."""
        with self.service._lock:
            self.service.check_lease(lease_hash)
            self.check_attempt(profile_id, attempt_id, lease_hash)
            item = self.attempts[attempt_id]
            if time.monotonic() >= item.expires_at and not item.settled:
                item.cancelled.set()
                item.progress.status = "expired"
            active = (
                item.progress.status == "connecting" and not item.cancelled.is_set()
            )
            return {
                "progress": item.progress.model_dump(mode="json"),
                "authorization_url": (
                    item.authorization_url.get_secret_value()
                    if active and item.authorization_url
                    else None
                ),
                "user_code": (
                    item.user_code.get_secret_value()
                    if active and item.user_code
                    else None
                ),
                "replacement_account": (
                    item.identity.model_dump()
                    if item.progress.status == "awaiting_confirmation" and item.identity
                    else None
                ),
            }

    def progress(self, profile_id, attempt_id):
        """Read a safe progress receipt, never its one-use device code."""
        with self.service._lock:
            item = self.attempts.get(attempt_id)
            if item is None or item.profile_id != profile_id:
                raise ProviderConnectionError("provider_login_expired")
            if time.monotonic() >= item.expires_at and not item.settled:
                item.cancelled.set()
                item.progress.status = "expired"
            return item.progress.model_copy()

    def confirm(self, profile_id, attempt_id, *, lease_hash):
        """Confirm the observed candidate; the worker alone publishes after fencing."""
        with self.service._lock:
            self.details(profile_id, attempt_id, lease_hash=lease_hash)
            item = self.attempts[attempt_id]
            if (
                item.progress.status != "awaiting_confirmation"
                or item.cancelled.is_set()
            ):
                raise ProviderConnectionError("provider_login_expired")
            item.confirmation.set()
            item.progress.status = "verifying"
            return item.progress.model_copy()

    def owns(self, vault):
        """Keep unmarked retained Codex revisions after other provider markers."""
        return True

    def native(self, profile_id, record):
        """Resolve exact native custody; the SIWC revision is never converted."""
        return CodexNativeCredentials(self._root(profile_id, record.credential_id))

    def profile(self, profile_id, record):
        """Admit only this unchanged native revision's existing owned volume."""
        if record.provider != "codex" or record.client_id != "codex-native":
            raise ProviderConnectionError("provider_connection_unavailable")
        return self.native(profile_id, record).profile()

    def saved_identity(self, profile_id, record):
        """Read verified public metadata; no token refresh or native process is started."""
        try:
            identity = CodexAccountIdentity.model_validate_json(
                (
                    self._root(profile_id, record.credential_id) / "codex-identity.json"
                ).read_bytes()
            )
            if identity.subject_hash() != record.subject_hash:
                raise ValueError()
            return identity
        except (OSError, ValueError):
            raise ProviderConnectionError("provider_connection_changed") from None

    def summary(self, profile_id, record):
        """Read local verified custody; never open a concurrent native writer."""
        if record.client_id != "codex-native":
            return self.retained.summary(profile_id, record)
        state = "unavailable"
        try:
            self.profile(profile_id, record)
            self.saved_identity(profile_id, record)
            state = "ready"
        except Exception:
            pass
        return ConnectionSummary(
            connection_id=record.connection_id,
            label=record.label,
            generation=record.generation,
            auth_state=state,
            lifecycle=record.lifecycle,
        )

    def borrow(self, profile_id, connection_id, generation):
        """Retained token-sharing revisions remain usable until explicit replacement."""
        record = self.service.admitted(profile_id, connection_id, generation)
        if record.client_id == "codex-native":
            raise ProviderConnectionError("provider_method_unavailable")
        return self.retained.borrow(profile_id, connection_id, generation)

    def _broker(self, profile_id, credential_id):
        """Resolve only an already-saved token-sharing revision during transition."""
        return self.retained._broker(profile_id, credential_id)

    def reconcile_orphan(self, root, active=False):
        """Discard uncommitted native revisions; never replay an interrupted login."""
        if (root / "codex-custody.json").exists():
            if not active:
                self.erase(root)
        else:
            self.retained.reconcile_orphan(root, active=active)

    def erase(self, root):
        """Confirm exact native cleanup before dropping host ownership metadata."""
        CodexNativeCredentials(root).erase()

    def erase_revision(self, profile_id, record):
        """Remove only the fenced admitted credential kind, with no remote revoke."""
        if record.client_id == "codex-native":
            self.erase(self._root(profile_id, record.credential_id))
        else:
            self.retained.erase_revision(profile_id, record)

    @staticmethod
    def spec(descriptor, mode):
        """Fixed auth-only sandbox; no project or tool mounts, no ambient credentials."""
        from py_docker.containers.models import ContainerSpec, Mount

        if mode not in {"login", "identity"}:
            raise ProviderConnectionError("provider_request_refused")
        return ContainerSpec(
            image=descriptor.image_id,
            name="laomedo-codex-auth-" + uuid4().hex,
            entrypoint=["node"],
            command=["/opt/acp/native-login.mjs", mode],
            init=True,
            user="10001:10001",
            working_dir="/draft",
            network_mode="bridge",
            stdin_open=False,
            mounts=[
                Mount(
                    type="volume", source=descriptor.name, target="/home/runner/.codex"
                )
            ],
            environment={"HOME": "/home/runner", "CODEX_HOME": "/home/runner/.codex"},
            log_driver="none",
            tmpfs={"/tmp": "rw,nosuid,nodev,size=64m,mode=1777"},
            nano_cpus=2_000_000_000,
        )

    def _check_live(self, item):
        """Fence expiry, cancellation, logout and stale replacement before publication."""
        self.service.check_lease(item.lease_hash)
        if item.cancelled.is_set() or time.monotonic() >= item.expires_at:
            raise ProviderConnectionError("provider_login_expired")
        if item.previous:
            if (
                self.service.admitted(item.profile_id, item.candidate_id)
                != item.previous
            ):
                raise ProviderConnectionError("provider_connection_changed")
            if (
                self.service.controllers is not None
                and self.service.controllers.inventory(
                    item.profile_id, item.candidate_id
                )[0]
            ):
                raise ProviderConnectionError("provider_connection_busy")

    def _run(self, item):
        """Own staging, native teardown, explicit replacement and exact publication."""
        from py_docker.sessions.models import ContainerSession
        from py_docker.streams.models import StreamLimits

        root = self._root(item.profile_id, item.credential_id)
        committed = False
        custody = CodexNativeCredentials(root)
        try:
            root.mkdir(mode=0o700)
            _restrict_windows_directory(root)
            with DockerRuntime(environment=None).connect() as docker:
                image_id = DockerRuntime.ensure_image(
                    docker, IMAGE, cancelled=item.cancelled
                )
                with self.service._lock:
                    self._check_live(item)
                custody.create(docker, item.candidate_id, item.credential_id, image_id)
            with custody.lease() as descriptor:
                receipt = root / "native-login-session.json"
                custody.register(receipt)
                with custody._client(descriptor) as docker:
                    with DockerRuntime.session(
                        docker,
                        ContainerSession(
                            spec=self.spec(descriptor, "login"),
                            limits=StreamLimits(
                                seconds=max(1, item.expires_at - time.monotonic()),
                                max_bytes=16384,
                            ),
                            receipt_path=receipt,
                        ),
                        deadline=item.expires_at,
                        cleanup_seconds=NATIVE_AUTH_CLEANUP_SECONDS,
                    ) as session:
                        with self.service._lock:
                            item.session = session
                        pending = b""
                        seen_device = seen_identity = False
                        with session.stop_on(item.cancelled.is_set):
                            while True:
                                frame = session.read_frame()
                                if frame is None:
                                    break
                                pending += frame.data
                                if len(pending) > 16384:
                                    raise ValueError()
                                while b"\n" in pending:
                                    line, pending = pending.split(b"\n", 1)
                                    value = json.loads(line)
                                    if (
                                        value.get("type") == "device"
                                        and not seen_device
                                        and not seen_identity
                                        and set(value)
                                        == {"type", "authorization_url", "user_code"}
                                    ):
                                        if (
                                            value["authorization_url"]
                                            != "https://auth.openai.com/codex/device"
                                            or not isinstance(value["user_code"], str)
                                            or not 4 <= len(value["user_code"]) <= 32
                                        ):
                                            raise ValueError()
                                        with self.service._lock:
                                            self._check_live(item)
                                            item.authorization_url = SecretStr(
                                                value["authorization_url"]
                                            )
                                            item.user_code = SecretStr(
                                                value["user_code"]
                                            )
                                            item.ready.set()
                                        seen_device = True
                                    elif (
                                        value.get("type") == "identity"
                                        and seen_device
                                        and not seen_identity
                                    ):
                                        identity = CodexAccountIdentity.model_validate(
                                            {
                                                k: v
                                                for k, v in value.items()
                                                if k != "type"
                                            }
                                        )
                                        seen_identity = True
                                    else:
                                        raise ValueError()
                            if (
                                pending.strip()
                                or not seen_identity
                                or session.wait(5) != 0
                            ):
                                raise ProviderConnectionError("provider_sign_in_failed")
            # No browser confirmation is requested until exact container cleanup settles.
            with self.service._lock:
                self._check_live(item)
                item.identity = identity
                item.authorization_url = item.user_code = None
                item.progress.status = (
                    "awaiting_confirmation" if item.previous else "verifying"
                )
                item.ready.set()
            if item.previous:
                while not item.confirmation.wait(0.1):
                    with self.service._lock:
                        self._check_live(item)
            with self.service._lock:
                self._check_live(item)
                rows = self.service._records(item.profile_id)
                duplicate = next(
                    (
                        row
                        for row in rows
                        if row.provider == "codex"
                        and row.connection_id != item.candidate_id
                        and row.subject_hash == identity.subject_hash()
                    ),
                    None,
                )
                if duplicate:
                    item.progress.status = "duplicate"
                    item.progress.connection_id = duplicate.connection_id
                else:
                    _atomic_private(root / "codex-identity.json", identity.model_dump())
                    record = ConnectionRecord(
                        provider="codex",
                        connection_id=item.candidate_id,
                        credential_id=item.credential_id,
                        client_id="codex-native",
                        subject_hash=identity.subject_hash(),
                        generation=item.previous.generation + 1 if item.previous else 1,
                        label=identity.email,
                    )
                    try:
                        self.service._save(
                            item.profile_id,
                            [
                                row
                                for row in rows
                                if row.connection_id != item.candidate_id
                            ]
                            + [record],
                        )
                    except Exception:
                        committed = True  # Unknown readback must retain staged custody.
                        if record not in self.service._records(item.profile_id):
                            committed = False
                            raise
                    committed = True
                    item.progress.status = "connected"
                    item.progress.connection_id = item.candidate_id
            if committed and item.previous:
                try:
                    self.erase_revision(item.profile_id, item.previous)
                except Exception:
                    item.progress.code = "provider_cleanup_unconfirmed"
        except Exception as failure:
            logging.getLogger(__name__).warning(
                "Codex native sign-in failed: exception_type=%s", type(failure).__name__
            )
            with self.service._lock:
                if item.progress.status not in {"cancelled", "expired", "duplicate"}:
                    item.progress.status = (
                        "expired"
                        if not committed and time.monotonic() >= item.expires_at
                        else "failed"
                    )
                    item.progress.code = (
                        "provider_save_unconfirmed"
                        if committed
                        else "provider_sign_in_failed"
                    )
        finally:
            if not committed and (root / "codex-custody.json").exists():
                try:
                    custody.erase()
                except Exception:
                    item.progress.status = "failed"
                    item.progress.code = "provider_cleanup_unconfirmed"
            with self.service._lock:
                item.session = None
                item.authorization_url = item.user_code = None
                item.settled = True
                item.ready.set()
