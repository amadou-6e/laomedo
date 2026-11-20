"""Official-client Claude sign-in in connection-owned Docker profiles."""

import json
import logging
import re
import threading
import time
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

from pydantic import SecretStr

from laomedo.agents.agents.claude.settings import IMAGE
from laomedo.docker import DockerRuntime
from laomedo.host.credentials.siwc.utils import _atomic_private
from laomedo.host.credentials.siwc.utils import _restrict_windows_directory
from laomedo.agents.connections.base import BaseProviderConnection
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.agents.claude.models import ClaudeLoginAttempt
from laomedo.agents.agents.claude.models import ClaudeNativeProfile
from laomedo.agents.agents.claude.models import ClaudeAccountIdentity
from laomedo.agents.connections.models import ConnectionRecord
from laomedo.agents.connections.models import ConnectionSummary
from laomedo.agents.connections.models import LoginProgress
from laomedo.agents.connections.settings import ATTEMPT_SECONDS
from laomedo.agents.connections.settings import MAX_CONNECTIONS
from laomedo.agents.agents.claude.settings import NATIVE_AUTH_CLEANUP_SECONDS


class ClaudeConnection(BaseProviderConnection):
    """Keep all authentication and refresh inside the unmodified official client.

    The host relays only the native authorize URL and one-use completion code.
    It never reads, exchanges, mirrors or exports the client's login tokens.
    Each attempt uses a fresh profile so failed reconnect preserves the old one.
    """

    provider = "claude"
    cleanup_seconds = NATIVE_AUTH_CLEANUP_SECONDS
    summary_outside_lock = True

    def __init__(self, service):
        """Bind the shared owner lock; native startup occurs only in begin()."""
        self.service = service
        self.attempts = {}
        self._resource_locks = {}

    def validate_identity(self, record, auth):
        """Match the official native account/workspace to its admitted revision."""
        identity = ClaudeAccountIdentity(
            email=auth.get("email"), organization_id=auth.get("orgId")
        )
        if identity.subject_hash() != record.subject_hash:
            raise ValueError()

    def profile(self, profile_id, record):
        """Require the exact owned volume; absence never selects a host login."""
        if record.provider != "claude":
            raise ProviderConnectionError("provider_connection_unavailable")
        descriptor = self._descriptor(self._root(profile_id, record.credential_id))
        with self._client(descriptor) as docker:
            if docker.volumes.inspect(self._identity(descriptor)) is None:
                raise ProviderConnectionError("provider_connection_unavailable")
        return descriptor

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
            if previous and previous.provider != "claude":
                raise ProviderConnectionError("provider_method_unavailable")
            if (
                previous
                and self.service.controllers.inventory(profile_id, connection_id)[0]
            ):
                raise ProviderConnectionError("provider_connection_busy")
            attempt_id = uuid4()
            item = ClaudeLoginAttempt(
                profile_id=profile_id,
                lease_hash=lease_hash,
                candidate_id=connection_id or uuid4(),
                credential_id=uuid4(),
                previous=previous,
                expires_at=time.monotonic() + ATTEMPT_SECONDS,
                progress=LoginProgress(
                    attempt_id=attempt_id, status="connecting", provider="claude"
                ),
                cancelled=threading.Event(),
                ready=threading.Event(),
            )
            self.attempts[attempt_id] = item
            item.worker = threading.Thread(target=self._run, args=(item,), daemon=True)
            item.worker.start()
        item.ready.wait(8)
        return self.details(profile_id, attempt_id)

    def details(self, profile_id, attempt_id, *, lease_hash=None):
        """Observe this owner's receipt and native URL without replaying sign-in."""
        with self.service._lock:
            item = self.attempts.get(attempt_id)
            if item is None or item.profile_id != profile_id:
                raise ProviderConnectionError("provider_login_expired")
            if lease_hash is not None:
                self.service.check_lease(lease_hash)
                if item.lease_hash != lease_hash:
                    raise ProviderConnectionError("provider_login_expired")
            if time.monotonic() >= item.expires_at and item.progress.status in {
                "connecting",
                "verifying",
            }:
                item.cancelled.set()
                item.progress.status = "expired"
            return {
                "progress": item.progress.model_dump(mode="json"),
                "authorization_url": (
                    item.authorization_url.get_secret_value()
                    if item.authorization_url and item.progress.status == "connecting"
                    else None
                ),
            }

    def submit(self, profile_id, attempt_id, code: SecretStr, *, lease_hash):
        """Relay one use of a native completion code; never exchange or store it."""
        value = code.get_secret_value()
        if (
            not value
            or len(value) > 4096
            or any(character.isspace() for character in value)
        ):
            raise ProviderConnectionError("provider_request_refused")
        with self.service._lock:
            self.details(profile_id, attempt_id)
            item = self.attempts[attempt_id]
            if (
                item.lease_hash != lease_hash
                or lease_hash in self.service.revoked_leases
                or item.cancelled.is_set()
                or item.submitted
                or item.session is None
                or item.progress.status != "connecting"
            ):
                raise ProviderConnectionError("provider_login_expired")
            item.submitted = True
            item.progress.status = "verifying"
            session = item.session
        session.write((value + "\n").encode())
        return item.progress.model_copy()

    def cancel(self, profile_id, attempt_id):
        """Fence an exact attempt; the creator thread confirms native cleanup."""
        with self.service._lock:
            item = self.attempts.get(attempt_id)
            if item is None or item.profile_id != profile_id:
                raise ProviderConnectionError("provider_login_expired")
            if item.progress.status in {"connecting", "verifying"}:
                item.progress.status = "cancelled"
                item.cancelled.set()
            return item.progress.model_copy()

    def summary(self, profile_id, record):
        """Observe the official client's identity; a runner outage is not logout."""
        state = "unavailable"
        try:
            descriptor = self.profile(profile_id, record)
            identity = self._auth_status(
                self._root(profile_id, record.credential_id), descriptor
            )
            state = (
                "ready"
                if identity.subject_hash() == record.subject_hash
                else "reauthorization_required"
            )
        except Exception:
            pass
        return ConnectionSummary(
            provider="claude",
            method="claude_native",
            connection_id=record.connection_id,
            label=record.label,
            generation=record.generation,
            auth_state=state,
            lifecycle=record.lifecycle,
        )

    def reconcile_orphan(self, root, active=False):
        """Retain exact custody on daemon failure and retry on the next startup."""
        if active:
            return
        from py_docker.errors import DockerOperationError

        # Invalid ownership metadata still prevents admission; it is not a
        # transient daemon failure and must never authorize guessed cleanup.
        self._descriptor(root)
        try:
            self.erase(root)
        except ProviderConnectionError as error:
            if error.code != "provider_cleanup_unconfirmed":
                raise
            logging.getLogger(__name__).warning(
                "Claude orphan cleanup pending; custody retained for startup retry"
            )
        except DockerOperationError:
            logging.getLogger(__name__).warning(
                "Claude orphan cleanup pending; custody retained for startup retry"
            )

    def erase(self, root):
        """Recover exact native receipts and remove only this owned volume."""
        from py_docker.errors import DockerOperationError

        try:
            descriptor = self._descriptor(root)
            with self._resource_lock(root):
                with self._client(descriptor) as docker:
                    for name, kind in (
                        ("claude-login-session.json", "session"),
                        ("claude-status-job.json", "job"),
                    ):
                        if (root / name).exists():
                            DockerRuntime.recover_receipts(
                                docker, [root / name], kind=kind
                            )
                    identity = self._identity(descriptor)
                    volume = docker.volumes.inspect(identity)
                    if volume is not None:
                        volume.remove(force=False)
                    if docker.volumes.inspect(identity) is not None:
                        raise ProviderConnectionError("provider_cleanup_unconfirmed")
                (root / "claude-custody.json").unlink()
        except DockerOperationError:
            raise ProviderConnectionError("provider_cleanup_unconfirmed") from None

    def has_attempt(self, attempt_id):
        """Identify a native login receipt without starting a client."""
        return attempt_id in self.attempts

    def progress(self, profile_id, attempt_id):
        """Project this native receipt through the common safe wire model."""
        return LoginProgress.model_validate(
            self.details(profile_id, attempt_id)["progress"]
        )

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

    def owns(self, vault):
        """Admit Claude custody before the unmarked Codex fallback."""
        return (vault / "claude-custody.json").exists()

    def erase_revision(self, profile_id, record):
        """Erase the exact native profile after its work has settled."""
        self.erase(self.service._profile(profile_id) / str(record.credential_id))

    def check_attempt(self, profile_id, attempt_id, lease_hash):
        """Verify the exact owner and opaque originating lease under the service lock."""
        item = self.attempts.get(attempt_id)
        if (
            item is None
            or item.profile_id != profile_id
            or item.lease_hash != lease_hash
        ):
            raise ProviderConnectionError("provider_login_expired")

    def _resource_lock(self, root):
        """Serialize one revision without delaying unrelated logout or cancellation."""
        with self.service._lock:
            return self._resource_locks.setdefault(str(root), threading.RLock())

    def _root(self, profile_id, credential_id) -> Path:
        """Resolve an opaque host-owned revision below the private profile root."""
        return self.service._profile(profile_id) / str(credential_id)

    def _descriptor(self, root: Path) -> ClaudeNativeProfile:
        """Read resource ownership only; this file never contains a login token."""
        try:
            return ClaudeNativeProfile.model_validate_json(
                (root / "claude-custody.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            raise ProviderConnectionError("provider_connection_unavailable") from None

    def _client(self, descriptor):
        """Pin every subsequent native operation to the original Docker daemon."""
        return DockerRuntime(
            environment={"DOCKER_HOST": descriptor.docker_endpoint}
        ).connect()

    def _identity(self, descriptor):
        """Reconstruct only the SDK's exact owned-volume descriptor."""
        from py_docker.volumes.models import VolumeIdentity

        return VolumeIdentity(name=descriptor.name, labels=descriptor.labels)

    def _create_profile(self, root, docker, item, image_id):
        """Persist exact ownership before daemon creation, including uncertain creation."""
        from py_docker.settings import OWNERSHIP_LABEL

        descriptor = ClaudeNativeProfile(
            name="laomedo-claude-connection-" + item.credential_id.hex,
            labels={
                "laomedo.provider": "claude",
                "laomedo.connection": str(item.candidate_id),
                OWNERSHIP_LABEL: uuid4().hex,
            },
            docker_endpoint=docker.connection.endpoint,
            image_id=image_id,
        )
        # Persist the exact owner token before daemon creation. A crash
        # or ambiguous create can therefore reconcile only this volume.
        _atomic_private(root / "claude-custody.json", descriptor.model_dump())
        docker.sdk.volumes.create(name=descriptor.name, labels=descriptor.labels)
        if docker.volumes.inspect(self._identity(descriptor)) is None:
            raise ProviderConnectionError("provider_cleanup_unconfirmed")
        return descriptor

    def _spec(self, descriptor, command, *, interactive=False):
        """Build an auth-only official-client sandbox without project or tool mounts."""
        from py_docker.containers.models import ContainerSpec, Mount

        return ContainerSpec(
            image=descriptor.image_id,
            name="laomedo-claude-auth-" + uuid4().hex,
            entrypoint=["claude"],
            command=command,
            init=True,
            working_dir="/draft",
            network_mode="bridge",
            stdin_open=interactive,
            mounts=[Mount(type="volume", source=descriptor.name, target="/profile")],
            environment={
                "HOME": "/profile",
                "CLAUDE_CONFIG_DIR": "/profile/config",
                "DISABLE_AUTOUPDATER": "1",
            },
            log_driver="none",
            tmpfs={"/tmp": "rw,nosuid,nodev,size=64m,mode=1777"},
            nano_cpus=2_000_000_000,
        )

    @staticmethod
    def _is_authorization_url(value):
        """Accept only exact native Claude authorization endpoints, never arbitrary redirects."""
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and (parsed.netloc, parsed.path)
            in {
                ("claude.ai", "/oauth/authorize"),
                ("platform.claude.com", "/oauth/authorize"),
                ("claude.com", "/cai/oauth/authorize"),
            }
            and not parsed.fragment
        )

    def _auth_status(self, root, descriptor):
        """Ask the native client for public identity without inference or token reads."""
        from py_docker.jobs.models import ContainerJob
        from py_docker.streams.models import StreamLimits

        with self._resource_lock(root), self._client(descriptor) as docker:
            result = DockerRuntime.execute_job(
                docker,
                ContainerJob(
                    spec=self._spec(descriptor, ["auth", "status"]),
                    limits=StreamLimits(seconds=25, max_bytes=16384),
                    receipt_path=root / "claude-status-job.json",
                    wait_timeout_seconds=5,
                ),
            )
        try:
            value = json.loads(result.stdout)
            if (
                result.exit_code
                or value.get("loggedIn") is not True
                or value.get("authMethod") != "claude.ai"
            ):
                raise ValueError()
            email, organization = value.get("email"), value.get("orgId")
            if not isinstance(email, str) or not email or len(email) > 100:
                raise ValueError()
            if not isinstance(organization, str) or not organization:
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            raise ProviderConnectionError("provider_sign_in_failed") from None
        return ClaudeAccountIdentity(email=email, organization_id=organization)

    def _run(self, item):
        """Own native sessions, one-use publication and exact resource cleanup."""
        from py_docker.sessions.models import ContainerSession
        from py_docker.streams.models import StreamLimits

        root = None
        committed = False
        stage = "custody"
        try:
            root = self._root(item.profile_id, item.credential_id)
            root.mkdir(mode=0o700)
            _restrict_windows_directory(root)
            with DockerRuntime(environment=None).connect() as docker:
                stage = "image"
                image_id = DockerRuntime.ensure_image(
                    docker, IMAGE, cancelled=item.cancelled
                )
                if item.cancelled.is_set() or time.monotonic() >= item.expires_at:
                    raise ProviderConnectionError("provider_login_expired")
                stage = "volume"
                descriptor = self._create_profile(root, docker, item, image_id)
                stage = "native_login"
                with DockerRuntime.session(
                    docker,
                    ContainerSession(
                        spec=self._spec(
                            descriptor,
                            ["auth", "login", "--claudeai"],
                            interactive=True,
                        ),
                        limits=StreamLimits(
                            seconds=max(1, item.expires_at - time.monotonic()),
                            max_bytes=65536,
                        ),
                        receipt_path=root / "claude-login-session.json",
                    ),
                    deadline=item.expires_at,
                    cleanup_seconds=NATIVE_AUTH_CLEANUP_SECONDS,
                ) as session:
                    with self.service._lock:
                        item.session = session
                    pending = ""
                    with session.stop_on(item.cancelled.is_set):
                        while True:
                            frame = session.read_frame()
                            if frame is None:
                                break
                            if item.authorization_url is None:
                                pending = (
                                    pending
                                    + frame.data.decode("utf-8", errors="ignore")
                                )[-16384:]
                                for match in re.finditer(
                                    r"https://[^\s\x1b\x07<>]+(?=[\s\x1b\x07<>])",
                                    pending,
                                ):
                                    url = match.group(0)
                                    if self._is_authorization_url(url):
                                        item.authorization_url = SecretStr(url)
                                        item.ready.set()
                        if session.wait(5) != 0:
                            raise ProviderConnectionError("provider_sign_in_failed")
            stage = "verify"
            identity = self._auth_status(root, descriptor)
            email, digest = identity.email, identity.subject_hash()
            with self.service._lock:
                if (
                    item.cancelled.is_set()
                    or time.monotonic() >= item.expires_at
                    or item.lease_hash in self.service.revoked_leases
                ):
                    raise ProviderConnectionError("provider_login_expired")
                rows = self.service._records(item.profile_id)
                if (
                    item.previous
                    and self.service.controllers.inventory(
                        item.profile_id, item.candidate_id
                    )[0]
                ):
                    raise ProviderConnectionError("provider_connection_busy")
                if item.previous and (
                    item.previous not in rows or item.previous.subject_hash != digest
                ):
                    raise ProviderConnectionError("provider_account_mismatch")
                duplicate = next(
                    (
                        row
                        for row in rows
                        if row.provider == "claude"
                        and row.connection_id != item.candidate_id
                        and row.subject_hash == digest
                    ),
                    None,
                )
                if duplicate:
                    item.progress.status = "duplicate"
                    item.progress.connection_id = duplicate.connection_id
                else:
                    record = ConnectionRecord(
                        provider="claude",
                        connection_id=item.candidate_id,
                        credential_id=item.credential_id,
                        client_id="claude-native",
                        subject_hash=digest,
                        generation=item.previous.generation + 1 if item.previous else 1,
                        label=email,
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
                        # Readback is required: a replace can commit before an
                        # error. If readback itself fails, retain native custody.
                        committed = True
                        if record not in self.service._records(item.profile_id):
                            committed = False
                            raise
                    committed = True
                    item.progress.status = "connected"
                    item.progress.connection_id = item.candidate_id
            if committed and item.previous:
                try:
                    self.erase(self._root(item.profile_id, item.previous.credential_id))
                except Exception:
                    # Publication is confirmed; only old-revision cleanup is uncertain.
                    item.progress.code = "provider_cleanup_unconfirmed"
        except Exception as failure:
            logging.getLogger(__name__).warning(
                "Claude sign-in failed: stage=%s exception_type=%s",
                stage,
                type(failure).__name__,
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
                        else (
                            "provider_account_mismatch"
                            if isinstance(failure, ProviderConnectionError)
                            and failure.code == "provider_account_mismatch"
                            else "provider_sign_in_failed"
                        )
                    )
        finally:
            if (
                not committed
                and root is not None
                and (root / "claude-custody.json").exists()
            ):
                try:
                    self.erase(root)
                except Exception:
                    item.progress.status = "failed"
                    item.progress.code = "provider_cleanup_unconfirmed"
            with self.service._lock:
                item.session = None
                item.authorization_url = None
                item.settled = True
                item.ready.set()
