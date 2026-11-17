"""Trusted-local orchestration of connection-owned isolated native Codex runners."""

import json
import threading
import time
from functools import partial
from pathlib import Path
from uuid import UUID
from urllib.parse import urlsplit

from laomedo.host.provider_connections.credentials import SavedConnectionCredential
from laomedo.host.provider_connections.errors import ProviderConnectionError
from laomedo.host.provider_connections.models import ControllerSlot
from laomedo.host.runner.http.server import RunnerServer
from laomedo.host.runner.http.handler import RunnerRequestHandler
from laomedo.agents.errors import RunnerError
from laomedo.agents.registry import AgentProviderRegistry
from laomedo.host.credentials.siwc.utils import _outside_git


class SavedRunnerRequestHandler(RunnerRequestHandler):
    """Keep the old runner protocol, with a saved-connection admission fence."""

    def _serve(self, method):
        """Track native-starting requests before crossing the lifecycle fence."""
        if not self._authorized():
            return
        parsed = urlsplit(self.path)
        parts = (parsed.path if method == "GET" else self.path).strip("/").split("/")
        guarded = (
            method == "GET" and parts == ["v1", "models"] and not parsed.query
        ) or (
            method == "POST"
            and (
                parts in (["v1", "runs"], ["v1", "runs", "async"])
                or (
                    len(parts) == 4
                    and parts[:2] == ["v1", "runs"]
                    and parts[3] == "resume"
                )
                or (
                    len(parts) == 5
                    and parts[:2] == ["v1", "runs"]
                    and parts[3:] == ["resume", "async"]
                )
            )
        )
        try:
            if guarded:
                self.server.manager.admit_operation(
                    self.server.slot, catalog=method == "GET"
                )
        except ProviderConnectionError as error:
            self._reply(
                409,
                {
                    "status": "failed",
                    "error_category": error.code,
                },
            )
            return
        except (OSError, ValueError, KeyError):
            self._reply(
                409,
                {"status": "failed", "error_category": "provider_runner_unavailable"},
            )
            return
        try:
            if method == "GET":
                super().do_GET()
            else:
                super().do_POST()
        finally:
            if guarded:
                with self.server.manager.service._lock:
                    self.server.slot.operations -= 1
                    if method == "GET":
                        self.server.slot.catalog_operations -= 1

    def do_GET(self):
        """Allow evidence reads after fencing; guard native catalogue startup."""
        self._serve("GET")

    def do_POST(self):
        """Guard new/resumed work while retaining cancellation and evidence routes."""
        self._serve("POST")

    def log_message(self, *_args):
        """Do not emit private request identifiers or native bodies to host logs."""


class SavedRunnerServer(RunnerServer):
    """Ephemeral loopback listener with an exact host-owned connection binding."""

    def __init__(self, manager, slot):
        """Bind only after native startup succeeds; no browser-supplied host config."""
        self.manager = manager
        self.slot = slot
        super().__init__(slot.runner, host="127.0.0.1", port=0)
        self.RequestHandlerClass = SavedRunnerRequestHandler


class ProviderControllers:
    """Own all saved-connection dispatch paths and durable native cleanup inventory.

    This is trusted single-user host orchestration. It is not a sandbox for
    hostile Langflow Python. Native model/controller and tools stay separated by
    the existing split Docker transport and its mandatory isolation checks.
    """

    _current = None

    def __init__(
        self,
        service,
        root: Path,
        skill_store: Path,
        source: Path | None,
        *,
        factory=None,
    ):
        """Bind host configuration only; constructor performs no login or model turn."""
        self.service = service
        self.root = _outside_git(root)
        self.skill_store = skill_store
        self.source = source
        if factory is None:
            factory = partial(AgentProviderRegistry.create_agent, "codex")
        self.factory = factory
        self.slots = {}
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.closed = False
        self._stopping = threading.Event()
        self._cleanups = {}
        service.controllers = self

    @classmethod
    def current(cls):
        """Resolve the sole explicitly installed local-profile host runtime."""
        if cls._current is None or cls._current.closed:
            raise ProviderConnectionError("provider_runner_unavailable")
        return cls._current

    def install(self):
        """Publish only one manager after receipt reconciliation completes."""
        if type(self)._current is not None and not type(self)._current.closed:
            raise ProviderConnectionError("provider_runner_unavailable")
        type(self)._current = self
        for profile in self.service.root.iterdir():
            if not profile.is_dir():
                continue
            try:
                profile_id = UUID(profile.name)
            except ValueError:
                continue
            for record in self.service._records(profile_id):
                if record.lifecycle == "disconnecting":
                    self.continue_cleanup(profile_id, record.connection_id)

    def continue_cleanup(self, profile_id, connection_id):
        """Finish an already-confirmed removal as owned native work winds down."""
        key = (profile_id, connection_id)
        with self.service._lock:
            previous = self._cleanups.get(key)
            if self.closed or (previous is not None and previous.is_alive()):
                return
            worker = threading.Thread(
                target=self._finish_cleanup, args=key, daemon=True
            )
            self._cleanups[key] = worker
            worker.start()

    def _finish_cleanup(self, profile_id, connection_id):
        """Poll owned stop state only; no replay, login or model request occurs."""
        while not self._stopping.wait(1):
            try:
                result = self.service.retry_cleanup(profile_id, connection_id)
            except (ProviderConnectionError, OSError, ValueError):
                return
            if result.status != "disconnecting":
                return

    def recover(self):
        """Reconcile recorded owned controllers before dispatch, without replaying turns."""
        for profile in self.root.iterdir():
            if not profile.is_dir():
                continue
            try:
                profile_id = UUID(profile.name)
            except ValueError:
                continue
            for connection in profile.iterdir():
                if not connection.is_dir():
                    continue
                try:
                    connection_id = UUID(connection.name)
                except ValueError:
                    continue
                for state in connection.glob("g[0-9]*"):
                    if not state.is_dir() or not state.name[1:].isdigit():
                        continue
                    generation = int(state.name[1:])
                    if state.name != "g" + str(generation):
                        continue
                    try:
                        self.service._record(profile_id, connection_id)
                    except ProviderConnectionError:
                        if any((state / "receipts").glob("*.json")) or any(
                            state.glob("*/*receipt*.json")
                        ):
                            raise ProviderConnectionError(
                                "provider_cleanup_unconfirmed"
                            ) from None
                        continue
                    # Existing state, including fenced rows, must be reconciled
                    # before borrowing. Agent startup recovers exact receipts.
                    try:
                        self._create(
                            profile_id, connection_id, generation, recovery=True
                        )
                    except (RunnerError, OSError, ValueError):
                        # Keep the failed slot: Settings remains available, but
                        # removal must retry recovery before confirming cleanup.
                        continue

    def _create(self, profile_id, connection_id, generation, *, recovery=False):
        """Reserve startup before slow Docker work so disconnect cannot miss it."""
        key = (profile_id, connection_id, generation)
        with self.service._lock:
            if self.closed:
                raise ProviderConnectionError("provider_runner_unavailable")
            if not recovery:
                self.service.admitted(profile_id, connection_id, generation)
            existing = self.slots.get(key)
            if existing and (existing.creating or existing.server is not None):
                return existing
            state = (
                self.root
                / str(profile_id)
                / str(connection_id)
                / ("g" + str(generation))
            )
            slot = ControllerSlot(
                profile_id=profile_id,
                connection_id=connection_id,
                generation=generation,
                state=state,
                revision=existing.revision + 1 if existing else 1,
            )
            self.slots[key] = slot
        try:
            if self.source is None:
                raise ProviderConnectionError("provider_runner_unavailable")
            auth = SavedConnectionCredential(
                self.service, profile_id, connection_id, generation
            )
            runner = self.factory(
                state,
                self.skill_store,
                self.source,
                split_executor=True,
                auth_connection=auth,
            )
            with self.service._lock:
                slot.runner = runner
                slot.server = SavedRunnerServer(self, slot)
                threading.Thread(target=slot.server.serve_forever, daemon=True).start()
            return slot
        finally:
            with self.service._lock:
                slot.creating = False

    def endpoint(self, profile_id, connection_id, *, run_id=None):
        """Return a host-only URL/token path; retained runs resolve their original epoch."""
        with self.service._lock:
            if run_id:
                UUID(run_id)
                matches = [
                    slot
                    for slot in self.slots.values()
                    if slot.profile_id == profile_id
                    and slot.connection_id == connection_id
                    and (slot.state / "runs" / run_id / "record.json").is_file()
                ]
                if len(matches) != 1:
                    raise ProviderConnectionError("provider_connection_unavailable")
                slot = matches[0]
            else:
                record = self.service.admitted(profile_id, connection_id)
                slot = None
        if slot is None:
            slot = self._create(profile_id, connection_id, record.generation)
        deadline = time.monotonic() + 120
        while slot.creating and time.monotonic() < deadline:
            time.sleep(0.05)
        if slot.creating or slot.server is None:
            raise ProviderConnectionError("provider_runner_unavailable")
        return (
            "http://127.0.0.1:" + str(slot.server.server_address[1]),
            slot.state / "api-token",
        )

    def admit_operation(self, slot, *, catalog=False):
        """Atomically fence work admission and increment the confirmation revision."""
        with self.service._lock:
            if self.closed:
                raise ProviderConnectionError("provider_runner_unavailable")
            self.service.admitted(slot.profile_id, slot.connection_id, slot.generation)
            if slot.catalog_operations or (
                catalog
                and (
                    slot.operations
                    or slot.runner.lock.locked()
                    or slot.runner.pending_resumes()
                    or any(
                        record["status"] in {"prepared", "running"}
                        for record in self._records(slot)
                    )
                )
            ):
                raise ProviderConnectionError("provider_connection_busy")
            slot.operations += 1
            if catalog:
                slot.catalog_operations += 1
            slot.revision += 1

    def inventory(self, profile_id, connection_id):
        """Count owned active records and discovery/startup without launching anything."""
        count, revision = 0, 0
        for slot in self.slots.values():
            if slot.profile_id != profile_id or slot.connection_id != connection_id:
                continue
            revision += slot.revision
            active = {
                record["run_id"]
                for record in self._records(slot)
                if record["status"] in {"prepared", "running"}
            }
            if slot.runner is not None:
                active.update(item["run_id"] for item in slot.runner.pending_resumes())
            running = len(active)
            count += max(
                running,
                slot.operations,
                int(slot.runner is not None and slot.runner.lock.locked()),
            ) + int(slot.creating)
        return count, revision

    def _records(self, slot):
        """Read only this slot's retained run inventory; malformed state fails closed."""
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in (slot.state / "runs").glob("*/record.json")
        ]

    def stop(self, profile_id, connection_id):
        """Cancel exact owned runs; unknown receipt cleanup never counts as removed."""
        with self.service._lock:
            slots = [
                slot
                for slot in self.slots.values()
                if slot.profile_id == profile_id and slot.connection_id == connection_id
            ]
        ready = True
        for slot in slots:
            if slot.creating:
                ready = False
                continue
            if slot.runner is None:
                # Retry native construction to reconcile any receipt left by
                # the failed attempt. Never discard a receipt or fake success.
                try:
                    slot = self._create(
                        slot.profile_id,
                        slot.connection_id,
                        slot.generation,
                        recovery=True,
                    )
                except (RunnerError, OSError, ValueError):
                    raise ProviderConnectionError(
                        "provider_cleanup_unconfirmed"
                    ) from None
                if slot.creating or slot.runner is None:
                    ready = False
                    continue
            try:
                resumes = slot.runner.pending_resumes()
                if any(item["status"] == "unknown" for item in resumes):
                    raise ProviderConnectionError("provider_cleanup_unconfirmed")
                pending = {item["run_id"] for item in resumes}
                for record in self._records(slot):
                    if (
                        record["status"] in {"prepared", "running"}
                        or record["run_id"] in pending
                    ):
                        slot.runner.cancel(record["run_id"])
                        ready = False
                if (
                    slot.operations
                    or slot.runner.lock.locked()
                    or slot.runner.pending_resumes()
                ):
                    ready = False
                    continue
                if any((slot.state / "receipts").glob("*.json")) or any(
                    slot.state.glob("*/*receipt*.json")
                ):
                    slot.runner._check_container()
                if any((slot.state / "receipts").glob("*.json")) or any(
                    slot.state.glob("*/*receipt*.json")
                ):
                    raise ProviderConnectionError("provider_cleanup_unconfirmed")
            except (RunnerError, OSError, ValueError, KeyError):
                raise ProviderConnectionError("provider_cleanup_unconfirmed") from None
        return ready

    def close(self):
        """Fence new work, request cancellation and close only owned listeners."""
        with self.service._lock:
            self.closed = True
            self._stopping.set()
        for worker in list(self._cleanups.values()):
            worker.join()
        for slot in list(self.slots.values()):
            for record in self._records(slot):
                if slot.runner and record["status"] in {"prepared", "running"}:
                    slot.runner.cancel(record["run_id"])
            if slot.server:
                slot.server.shutdown()
                slot.server.server_close()
        if type(self)._current is self:
            type(self)._current = None
