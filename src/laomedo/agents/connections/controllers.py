"""Trusted-local orchestration of connection-owned isolated native provider runners."""

import json
import subprocess
import threading
import time
from functools import partial
from pathlib import Path
from uuid import UUID
from urllib.parse import urlsplit

from laomedo.agents.connections.credentials import (
    SavedConnectionCredential,
    SavedNativeCodexConnection,
)
from laomedo.agents.connections.credentials import SavedClaudeConnection
from laomedo.docker import DockerRuntime
from laomedo.agents.connections.errors import ProviderConnectionError
from laomedo.agents.connections.models import ControllerSlot
from laomedo.host.runner.http.server import RunnerServer
from laomedo.host.runner.http.handler import RunnerRequestHandler
from laomedo.agents.errors import RunnerError
from laomedo.agents.registry import AgentProviderRegistry
from laomedo.host.credentials.siwc.utils import _outside_git


class SavedRunnerRequestHandler(RunnerRequestHandler):
    """Keep the old runner protocol, with a saved-connection admission fence."""

    def do_GET(self):
        """Allow evidence reads after fencing; guard native catalogue startup."""
        self._serve("GET")

    def do_POST(self):
        """Guard new/resumed work while retaining cancellation and evidence routes."""
        self._serve("POST")

    def log_message(self, *_args):
        """Do not emit private request identifiers or native bodies to host logs."""

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
                failure=error,
            )
            return
        except (OSError, ValueError, KeyError) as error:
            self._reply(
                409,
                {"status": "failed", "error_category": "provider_runner_unavailable"},
                failure=error,
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

    def recover(self):
        """Inventory both fixed scopes before any pending disconnect can finish."""
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
                for scope, parent in (
                    ("graph", connection),
                    ("assistant", connection / "assistant"),
                ):
                    for epoch in parent.glob("g[0-9]*"):
                        if not epoch.is_dir() or not epoch.name[1:].isdigit():
                            continue
                        generation = int(epoch.name[1:])
                        if epoch.name != "g" + str(generation):
                            continue
                        state = epoch if scope == "graph" else epoch / "state"
                        if not state.is_dir():
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
                        try:
                            self._create(
                                profile_id,
                                connection_id,
                                generation,
                                recovery=True,
                                scope=scope,
                            )
                        except (
                            RunnerError,
                            OSError,
                            ValueError,
                        ) + self._native_failures():
                            # Preserve the failed slot and receipts for explicit cleanup retry.
                            continue

    def assistant_endpoint(self, profile_id, connection_id, generation, *, run_id=None):
        """Resolve only this account epoch's isolated chat; never graph state."""
        with self.service._lock:
            slot = self.slots.get((profile_id, connection_id, generation, "assistant"))
            if run_id is not None:
                run_id = str(UUID(str(run_id)))
                if (
                    slot is None
                    or not (slot.state / "runs" / run_id / "record.json").is_file()
                ):
                    raise ProviderConnectionError("provider_connection_unavailable")
            else:
                self.service.admitted(profile_id, connection_id, generation)
        if slot is None:
            slot = self._create(
                profile_id, connection_id, generation, scope="assistant"
            )
        deadline = time.monotonic() + 120
        while slot.creating and time.monotonic() < deadline:
            time.sleep(0.05)
        if slot.creating or slot.server is None:
            raise ProviderConnectionError("provider_runner_unavailable")
        return (
            "http://127.0.0.1:" + str(slot.server.server_address[1]),
            slot.state / "api-token",
        )

    def assistant_instance_id(self, profile_id, connection_id, generation):
        """Observe retained host identity without authorizing a new native operation."""
        slot = self.slots.get((profile_id, connection_id, generation, "assistant"))
        return (
            slot.runner.instance_id
            if slot is not None and slot.runner is not None
            else None
        )

    def assistant_live_session(self, profile_id, connection_id, generation, run_id):
        """Observe actual retained native ownership in this exact assistant scope."""
        self.assistant_endpoint(profile_id, connection_id, generation, run_id=run_id)
        slot = self.slots[(profile_id, connection_id, generation, "assistant")]
        return slot.runner.has_live_session(run_id)

    def assistant_settled(self, profile_id, connection_id, generation, run_id):
        """Observe actual lock and MCP cleanup; a terminal record alone is insufficient."""
        self.assistant_endpoint(profile_id, connection_id, generation, run_id=run_id)
        slot = self.slots[(profile_id, connection_id, generation, "assistant")]
        return not slot.runner.lock.locked() and (
            slot.runner.mcp_access(run_id) is None
            or slot.runner.has_live_session(run_id)
        )

    def connection_for_run(self, profile_id, run_id, *, scope="graph"):
        """Resolve a retained run from this owner's authoritative inventory, never preferences."""
        run_id = str(UUID(str(run_id)))
        with self.service._lock:
            matches = {
                slot.connection_id
                for slot in self.slots.values()
                if slot.profile_id == profile_id
                and slot.scope == scope
                and (slot.state / "runs" / run_id / "record.json").is_file()
            }
            if len(matches) != 1:
                raise ProviderConnectionError("provider_connection_unavailable")
            return matches.pop()

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
                    and slot.scope == "graph"
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

    def subscription_limits(self, binding):
        """Reserve the existing exact-account discovery fence until native teardown settles."""
        slot = self._create(
            binding.profile_id, binding.connection_id, binding.generation
        )
        deadline = time.monotonic() + 120
        while slot.creating and time.monotonic() < deadline:
            time.sleep(0.05)
        if slot.creating or slot.runner is None:
            raise ProviderConnectionError("provider_runner_unavailable")
        self.admit_operation(slot, catalog=True)
        try:
            return slot.runner.subscription_limits()
        finally:
            with self.service._lock:
                slot.operations -= 1
                slot.catalog_operations -= 1

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
                        (
                            record["status"] in {"prepared", "running"}
                            or (
                                slot.runner is not None
                                and slot.runner.has_live_session(record["run_id"])
                            )
                        )
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
                if (
                    record["status"] in {"prepared", "running"}
                    or (
                        slot.runner is not None
                        and slot.runner.has_live_session(record["run_id"])
                    )
                )
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

    def stop(self, profile_id, connection_id):
        """Cancel exact owned runs; unknown receipt cleanup never counts as removed."""
        with self.service._lock:
            slots = [
                slot
                for slot in self.slots.values()
                if slot.profile_id == profile_id and slot.connection_id == connection_id
            ]
        ready = True
        unconfirmed = False
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
                        scope=slot.scope,
                    )
                except (RunnerError, OSError, ValueError) + self._native_failures():
                    unconfirmed = True
                    continue
                if slot.creating or slot.runner is None:
                    ready = False
                    continue
            try:
                resumes = slot.runner.pending_resumes()
                if any(item["status"] == "unknown" for item in resumes):
                    unconfirmed = True
                pending = {item["run_id"] for item in resumes}
                for record in self._records(slot):
                    if (
                        record["status"] in {"prepared", "running"}
                        or (
                            slot.runner is not None
                            and slot.runner.has_live_session(record["run_id"])
                        )
                    ) or record["run_id"] in pending:
                        slot.runner.cancel(record["run_id"])
                        ready = False
                if (
                    slot.operations
                    or slot.runner.lock.locked()
                    or slot.runner.pending_resumes()
                ):
                    ready = False
                    continue
                if slot.runner.provider == "opencode":
                    slot.runner._recover_containers()
                    if any(slot.state.glob("runs/*/docker-receipts/*.json")) or any(
                        slot.state.glob("catalog/*/docker-receipts/*.json")
                    ):
                        raise ProviderConnectionError("provider_cleanup_unconfirmed")
                if any((slot.state / "receipts").glob("*.json")) or any(
                    slot.state.glob("*/*receipt*.json")
                ):
                    if slot.runner.provider == "claude":
                        with slot.runner.container.client() as docker:
                            DockerRuntime.recover_receipts(
                                docker,
                                list((slot.state / "receipts").glob("*.json")),
                                kind="session",
                            )
                    elif slot.runner.provider == "opencode":
                        slot.runner._recover_containers()
                    else:
                        slot.runner._check_container()
                if any((slot.state / "receipts").glob("*.json")) or any(
                    slot.state.glob("*/*receipt*.json")
                ):
                    raise ProviderConnectionError("provider_cleanup_unconfirmed")
            except (
                RunnerError,
                OSError,
                ValueError,
                KeyError,
            ) + self._native_failures():
                unconfirmed = True
        if unconfirmed:
            raise ProviderConnectionError("provider_cleanup_unconfirmed")
        return ready

    def close(self):
        """Fence new work, request cancellation and close only owned listeners."""
        with self.service._lock:
            self.closed = True
            self._stopping.set()
        for worker in list(self._cleanups.values()):
            worker.join()
        failures = []
        for slot in list(self.slots.values()):
            try:
                for record in self._records(slot):
                    if slot.runner and (
                        record["status"] in {"prepared", "running"}
                        or slot.runner.has_live_session(record["run_id"])
                    ):
                        slot.runner.cancel(record["run_id"])
            except Exception as error:
                failures.append(error)
            try:
                if slot.runner:
                    slot.runner.close()
            except Exception as error:
                failures.append(error)
            if slot.server:
                try:
                    slot.server.shutdown()
                except Exception as error:
                    failures.append(error)
                finally:
                    try:
                        slot.server.server_close()
                    except Exception as error:
                        failures.append(error)
        if type(self)._current is self:
            type(self)._current = None
        if failures:
            raise ProviderConnectionError("provider_cleanup_unconfirmed") from failures[
                0
            ]

    def _assistant_source(self, state):
        """Prepare only the fixed scratch sibling, never the graph repository."""
        repository = state.parent / "source"
        source = repository / "workspace"
        if not source.is_dir() and any((state / "runs").glob("*/record.json")):
            raise ProviderConnectionError("provider_cleanup_unconfirmed")
        source.mkdir(parents=True, exist_ok=True)
        if not (repository / ".git").is_dir():
            subprocess.run(
                ["git", "init", "--quiet", str(repository)],
                check=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=20,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        readme = source / "README.md"
        if not readme.exists():
            readme.write_text(
                "# Laomedo assistant scratch workspace\nUse scoped Laomedo MCP tools. This is not the user's repository.\n",
                encoding="utf-8",
            )
        return source

    def _finish_cleanup(self, profile_id, connection_id):
        """Poll owned stop state only; no replay, login or model request occurs."""
        while not self._stopping.wait(1):
            try:
                result = self.service.retry_cleanup(profile_id, connection_id)
            except (ProviderConnectionError, OSError, ValueError):
                return
            if result.status != "disconnecting":
                return

    @staticmethod
    def _native_failures():
        """Recognize native operational failures only when the optional SDK exists."""
        try:
            from py_docker.errors import DockerOperationError
        except ImportError:
            return ()
        return (DockerOperationError,)

    def _create(
        self, profile_id, connection_id, generation, *, recovery=False, scope="graph"
    ):
        """Reserve startup before slow Docker work so disconnect cannot miss it."""
        if scope not in {"graph", "assistant"}:
            raise ProviderConnectionError("provider_runner_unavailable")
        key = (profile_id, connection_id, generation, scope)
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
            if scope == "assistant":
                state = (
                    self.root
                    / str(profile_id)
                    / str(connection_id)
                    / "assistant"
                    / ("g" + str(generation))
                    / "state"
                )
            slot = ControllerSlot(
                scope=scope,
                profile_id=profile_id,
                connection_id=connection_id,
                generation=generation,
                state=state,
                revision=existing.revision + 1 if existing else 1,
            )
            self.slots[key] = slot
        try:
            source = self.source if scope == "graph" else self._assistant_source(state)
            if source is None:
                raise ProviderConnectionError("provider_runner_unavailable")
            record = self.service._record(profile_id, connection_id)
            options = {"artifact_sources": {}} if scope == "assistant" else {}
            if record.provider == "claude" and self.factory is None:
                auth = SavedClaudeConnection(
                    self.service, profile_id, connection_id, generation
                )
                native = self.service.claude.profile(profile_id, record)
                runner = AgentProviderRegistry.create_agent(
                    "claude",
                    state,
                    self.skill_store,
                    source,
                    **options,
                    profile_volume=native.name,
                    **({"image": native.image_id} if scope == "graph" else {}),
                    lease_service=self.root.parent / "provider-leases",
                    auth_connection=auth,
                )
            elif record.provider == "opencode" and self.factory is None:
                runner = AgentProviderRegistry.create_agent(
                    "opencode",
                    state,
                    self.skill_store,
                    source,
                    **options,
                    profile=self.service.go.profile(profile_id, record),
                )
            else:
                if record.provider != "codex":
                    raise ProviderConnectionError("provider_method_unavailable")
                auth_type = (
                    SavedNativeCodexConnection
                    if record.client_id == "codex-native"
                    else SavedConnectionCredential
                )
                auth = auth_type(self.service, profile_id, connection_id, generation)
                factory = self.factory or partial(
                    AgentProviderRegistry.create_agent, "codex"
                )
                runner = factory(
                    state,
                    self.skill_store,
                    source,
                    **options,
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

    def _records(self, slot):
        """Read only this slot's retained run inventory; malformed state fails closed."""
        return [
            json.loads(path.read_text(encoding="utf-8"))
            for path in (slot.state / "runs").glob("*/record.json")
        ]
