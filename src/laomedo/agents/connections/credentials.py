"""Exact saved-connection credential facade for the isolated native controller."""

from contextlib import contextmanager
from pathlib import Path
import json

from laomedo.host.credentials.siwc.connection import ChatGPTConnection
from laomedo.host.credentials.siwc.errors import AuthError
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.errors import RunnerError


class SavedConnectionCredential:
    """Keep every borrow and authorization probe behind the durable admission fence."""

    def __init__(self, service, profile_id, connection_id, generation):
        """Bind trusted host identity; never retain or import a token."""
        self.service = service
        self.profile_id = profile_id
        self.connection_id = connection_id
        self.generation = generation
        with service._lock:
            self.client_id = service._record(profile_id, connection_id).client_id

    def access_token(self, client_id):
        """Borrow this epoch only, mapping refusal to the existing auth boundary."""
        if client_id != self.client_id:
            raise AuthError("auth_account_mismatch")
        try:
            with self.service._lock:
                if (
                    self.service.controllers is not None
                    and self.service.controllers.closed
                ):
                    raise AuthError("auth_revoked")
                return self.service.borrow(
                    self.profile_id, self.connection_id, self.generation
                )
        except ProviderConnectionError:
            raise AuthError("auth_revoked") from None

    def account(self, client_id):
        """Read an admitted account without refreshing; disconnect invalidates it immediately."""
        if client_id != self.client_id:
            raise AuthError("auth_account_mismatch")
        try:
            with self.service._lock:
                if (
                    self.service.controllers is not None
                    and self.service.controllers.closed
                ):
                    raise AuthError("auth_revoked")
                record = self.service.admitted(
                    self.profile_id, self.connection_id, self.generation
                )
                account = self.service.codex._broker(
                    self.profile_id, record.credential_id
                ).account(client_id)
                return {**account, "connection_generation": record.generation}
        except ProviderConnectionError:
            raise AuthError("auth_revoked") from None

    def summary(self, account):
        """Preserve native observations and add the stable admission epoch for probes."""
        return {
            **ChatGPTConnection.summary(account),
            "connection_generation": account["connection_generation"],
        }


class SavedClaudeConnection:
    """Fence the official client's own profile without importing or reading tokens."""

    def __init__(self, service, profile_id, connection_id, generation):
        """Bind exact host-owned account identity and stable generation."""
        self.service = service
        self.profile_id = profile_id
        self.connection_id = connection_id
        self.generation = generation

    def check(self):
        """Require an admitted unchanged account and its exact native profile."""
        try:
            with self.service._lock:
                if self.service.controllers is None or self.service.controllers.closed:
                    raise ProviderConnectionError("provider_connection_unavailable")
                record = self.service.admitted(
                    self.profile_id, self.connection_id, self.generation
                )
            descriptor = self.service.claude.profile(self.profile_id, record)
            with self.service._lock:
                self.service.admitted(
                    self.profile_id, self.connection_id, self.generation
                )
            return descriptor
        except ProviderConnectionError as error:
            raise RunnerError(error.code) from None
        except Exception:
            raise RunnerError("provider_connection_unavailable") from None

    def validate(self, auth):
        """Match native account/workspace to the saved generation before admission."""
        self.check()
        try:
            with self.service._lock:
                record = self.service.admitted(
                    self.profile_id, self.connection_id, self.generation
                )
                self.service.adapter("claude").validate_identity(record, auth)
        except (ValueError, TypeError, AttributeError):
            raise RunnerError("provider_connection_changed") from None


class SavedNativeCodexConnection(SavedConnectionCredential):
    """Fence native custody and public identity without borrowing a bearer token."""

    def __init__(self, service, profile_id, connection_id, generation):
        """Bind the exact admitted native revision and its writer custody."""
        super().__init__(service, profile_id, connection_id, generation)
        record = service.admitted(profile_id, connection_id, generation)
        self.custody = service.codex.native(profile_id, record)

    def account(self, client_id):
        """Check generation and local verified metadata without starting a native writer."""
        if client_id != self.client_id:
            raise AuthError("auth_account_mismatch")
        try:
            with self.service._lock:
                if (
                    self.service.controllers is not None
                    and self.service.controllers.closed
                ):
                    raise ProviderConnectionError("provider_connection_unavailable")
                record = self.service.admitted(
                    self.profile_id, self.connection_id, self.generation
                )
                identity = self.service.codex.saved_identity(self.profile_id, record)
                return {
                    "state": "active",
                    "credential_ref": str(record.connection_id),
                    "provider_subject_hash": identity.subject_hash(),
                    "connection_generation": record.generation,
                    "credential_mode": "chatgpt_plan_oauth",
                    "auth_outcome": "verified",
                }
        except ProviderConnectionError:
            raise AuthError("auth_revoked") from None

    def summary(self, account):
        """Project the native binding, never a SIWC token or issuer claim."""
        return {key: value for key, value in account.items() if key != "state"}

    def access_token(self, client_id):
        """Return a no-token native binding; the official client owns its auth file."""
        return None, self.summary(self.account(client_id))

    def profile(self):
        """Validate exact admitted volume ownership on its original daemon."""
        self.account(self.client_id)
        return self.custody.profile()

    @contextmanager
    def lease(self):
        """Preserve stable runner failure codes when native custody refuses use."""
        try:
            with self._lease() as descriptor:
                yield descriptor
        except ProviderConnectionError as error:
            raise RunnerError(error.code) from None

    def register_runtime(self, receipt):
        """Record exact ACP custody before a native launch under the active lease."""
        self.custody.register(Path(receipt))

    @contextmanager
    def _lease(self):
        """Hold one native writer through identity verification and caller teardown."""
        from laomedo.docker import DockerRuntime
        from py_docker.jobs.models import ContainerJob
        from py_docker.streams.models import StreamLimits

        self.account(self.client_id)
        with self.custody.lease() as descriptor:
            receipt = self.custody.root / "native-identity-job.json"
            self.custody.register(receipt, kind="job")
            with self.custody._client(descriptor) as docker:
                result = DockerRuntime.execute_job(
                    docker,
                    ContainerJob(
                        spec=self.service.codex.spec(descriptor, "identity"),
                        limits=StreamLimits(seconds=100, max_bytes=16384),
                        receipt_path=receipt,
                        wait_timeout_seconds=5,
                    ),
                )
            try:
                value = json.loads(result.stdout)
                if result.exit_code or value.pop("type", None) != "identity":
                    raise ValueError()
                with self.service._lock:
                    record = self.service.admitted(
                        self.profile_id, self.connection_id, self.generation
                    )
                    self.service.codex.validate_native_identity(value, record)
            except (ValueError, TypeError, AttributeError):
                raise RunnerError("provider_connection_changed") from None
            self.account(self.client_id)
            yield descriptor
