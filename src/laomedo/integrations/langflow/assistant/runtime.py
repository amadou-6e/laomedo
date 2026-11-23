"""Application chat orchestration around existing provider, Activity and MCP boundaries."""

import asyncio
from contextlib import asynccontextmanager
import hashlib
import json
import logging
from pathlib import Path
import re
import secrets
import time
import traceback
from uuid import UUID

from sqlmodel import select

from laomedo.agents.agents.base.settings import RUNNER_FAILURE_CODES
from laomedo.agents.mcp.registry import McpRegistry
from laomedo.agents.mcp.settings import MCP_ERROR_CODES
from laomedo.integrations.langflow.assistant.catalog import ComponentCatalog
from laomedo.integrations.langflow.assistant.errors import AssistantError
from laomedo.integrations.langflow.assistant.models import (
    ModelCatalogCacheEntry,
    IdleAssistantTools,
    AuthoringContext,
    AssistantSession,
)
from laomedo.integrations.langflow.assistant.persistence import AssistantStore
from laomedo.integrations.langflow.assistant.runner import AssistantRunner
from laomedo.integrations.langflow.assistant.settings import (
    AUTHORING_SERVER_NAME,
    AUTHORING_TOOL_NAMES,
    AssistantSettings,
    ASSISTANT_INSTRUCTIONS,
)
from laomedo.integrations.langflow.assistant.workflows import WorkflowDrafts
from laomedo.integrations.langflow.mcp import LangflowMcpTool


class AssistantRuntime:
    """Own direct chat sessions without constructing an assistant workflow."""

    def __init__(self, settings):
        """Prepare inactive app composition without Docker, inference or credential reads."""
        self.settings = settings
        self.provider_connections = None
        self.idle_tools = {}
        self.claimed_idle_tools = {}
        self.model_catalogs = {}
        self.migration_blocked = False
        self.store = self.mcp = self.upstream = None
        self.runners, self.runner_locks, self.jobs = {}, {}, {}
        self.contexts, self.host_tokens, self.tool_tasks = {}, {}, {}
        self.save_locks, self.uncertain_saves = {}, {}
        self.graph_jobs = {}
        self.revoked_sessions = set()
        self.session_aliases = {}
        self.closing = False
        self.ready = False

    @classmethod
    def install(cls, app):
        """Install before the SPA fallback and compose with the existing registry lifespan."""
        from laomedo.integrations.langflow.assistant.mcp import AuthoringMcp
        from laomedo.integrations.langflow.assistant.routes import router
        from laomedo.integrations.langflow.assistant.boundary import AssistantBoundary

        owner = cls(AssistantSettings())
        app.state.laomedo_assistant = owner
        app.include_router(router)
        if owner.settings.app_url:
            owner.mcp = AuthoringMcp(owner, owner.settings.app_url)
            app.mount("/api/v1/laomedo/assistant/mcp", owner.mcp)
            app.add_middleware(
                AssistantBoundary, runtime=owner, origin=owner.settings.app_url
            )
        owner.upstream = app.router.lifespan_context
        app.router.lifespan_context = owner.lifespan
        return owner

    @asynccontextmanager
    async def lifespan(self, app):
        """Enter the MCP session manager exactly once, revoke/drain before parent teardown."""
        from langflow.services.deps import get_db_service

        self.store = AssistantStore(get_db_service().engine)
        # SQLModel metadata is shared with Langflow. Upgrade only already-owned
        # retained columns before its Alembic consistency check; fresh upstream
        # tables remain upstream's responsibility.
        await self.store.upgrade_retained()
        async with self.upstream(app) as state:
            self.provider_connections = getattr(app.state, "provider_connections", None)
            if self.mcp is None:
                yield state
                return
            await self.store.initialize()
            self.check_retired_runners()
            async with self.mcp.server.session_manager.run():
                idle_reaper = None
                self.ready = True
                try:
                    # Reservations remain reconcile-only after app restart. Native
                    # runners are inspected lazily after the owner authenticates.
                    for conversation in await self.store.pending():
                        await self.store.observe(
                            conversation.owner_id,
                            conversation.id,
                            conversation.active_message_id,
                            state="unknown",
                            error="assistant_dispatch_unknown",
                            reconciled=True,
                        )
                    from laomedo.integrations.langflow.assistant.actions import (
                        WorkflowActions,
                    )

                    await WorkflowActions(self.store, None, self.authorize).reconcile()
                    idle_reaper = asyncio.create_task(self._reap_idle_tools())
                    yield state
                finally:
                    self.closing = True
                    if idle_reaper is not None:
                        idle_reaper.cancel()
                        await asyncio.gather(idle_reaper, return_exceptions=True)
                    self.ready = False
                    self.host_tokens.clear()
                    for idle in list(self.idle_tools.values()):
                        await self.release_idle_session(
                            idle.context.owner_id, idle.context.conversation_id
                        )
                    cancellations = []
                    for conversation in await self.store.pending():
                        runner = self.runners.get(
                            self._runner_key(
                                conversation.owner_id,
                                conversation.provider,
                                conversation.connection_id,
                                conversation.connection_generation,
                            )
                        )
                        if runner is not None and conversation.run_id:
                            cancellations.append(
                                asyncio.to_thread(
                                    runner.request,
                                    "POST",
                                    "/v1/runs/" + conversation.run_id + "/cancel",
                                    {},
                                )
                            )
                    if cancellations:
                        # Revoke tool authority before requesting cancellation.
                        # An unfinished native turn remains unknown on restart;
                        # teardown never declares success or replays a prompt.
                        await asyncio.gather(*cancellations, return_exceptions=True)
                    for task in list(self.jobs.values()):
                        task.cancel()
                    await asyncio.gather(*self.jobs.values(), return_exceptions=True)
                    for task in list(self.graph_jobs.values()):
                        task.cancel()
                    await asyncio.gather(
                        *self.graph_jobs.values(), return_exceptions=True
                    )
                    for runner in self.runners.values():
                        await asyncio.to_thread(runner.shutdown)

    def require_ready(self):
        """Refuse unconfigured deployments without inventing a runner or app origin."""
        if not self.ready or self.closing:
            raise AssistantError("assistant_setup_required", 503)

    async def session(self, request, user):
        """Bind an actual verified native app JWT; API-key/external sessions are outside this slice."""
        import jwt
        from langflow.services.auth.utils import (
            get_jwt_verification_key,
            ACCESS_TOKEN_TYPE,
        )
        from langflow.services.deps import get_settings_service

        self.require_ready()
        token = self.request_token(request)
        if token is None:
            raise AssistantError("assistant_native_session_required", 403)
        settings = get_settings_service()
        try:
            payload = jwt.decode(
                token,
                get_jwt_verification_key(settings),
                algorithms=[settings.auth_settings.ALGORITHM],
            )
            if (
                UUID(payload["sub"]) != UUID(str(user.id))
                or payload.get("type") != ACCESS_TOKEN_TYPE
            ):
                raise ValueError()
            expires = float(payload["exp"])
        except (ValueError, KeyError, TypeError, jwt.PyJWTError):
            raise AssistantError("assistant_native_session_required", 403) from None
        fingerprint = hashlib.sha256(token.encode()).hexdigest()
        if self.provider_connections is not None:
            from laomedo.agents.connections.errors import ProviderConnectionError

            try:
                self.provider_connections.check_lease(fingerprint)
            except ProviderConnectionError:
                raise AssistantError("assistant_session_locked", 403) from None
        key = (
            self.provider_connections.resolve_lease(fingerprint)
            if self.provider_connections is not None
            else fingerprint
        )
        if fingerprint in self.revoked_sessions or key in self.revoked_sessions:
            raise AssistantError("assistant_session_locked", 403)
        renewal_key = key
        key = await self.store.admit_session(
            fingerprint,
            UUID(str(user.id)),
            expires,
            renewal_key=key if key != fingerprint else None,
        )
        self.session_aliases[fingerprint] = key
        self.session_aliases[renewal_key] = key
        await self.check_session(UUID(str(user.id)), key)
        return key

    def request_token(self, request):
        """Match upstream's native bearer-first, cookie-second credential selection."""
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            return header[7:]
        return request.cookies.get("access_token_lf")

    async def check_session(self, owner, key):
        """Recheck retained revocation, expiry and current user activity at release/dispatch."""
        from langflow.services.database.models.user.model import User

        if self.closing or key in self.revoked_sessions:
            raise AssistantError("assistant_session_locked", 403)
        if self.provider_connections is not None:
            from laomedo.agents.connections.errors import ProviderConnectionError

            try:
                self.provider_connections.check_lease(key)
            except ProviderConnectionError:
                raise AssistantError("assistant_session_locked", 403) from None
        async with self.store.sessions() as session:
            row = await session.get(AssistantSession, key)
            user = await session.get(User, owner)
            if (
                row is None
                or row.owner_id != owner
                or row.revoked
                or row.expires_at <= time.time()
                or user is None
                or not user.is_active
            ):
                raise AssistantError("assistant_session_locked", 403)
        if self.closing or key in self.revoked_sessions:
            raise AssistantError("assistant_session_locked", 403)

    async def authorize(self, context):
        """Fence a host tool binding both before and after asynchronous authority reads."""
        if self.contexts.get(context.message_id) != context:
            raise AssistantError("assistant_tool_authority_revoked", 403)
        await self.check_session(context.owner_id, context.session_key)
        async with self.store.sessions() as session:
            conversation = await self.store.conversation(
                session, context.owner_id, context.conversation_id
            )
        self.check_connection(
            context.owner_id,
            conversation.provider,
            conversation.connection_id,
            conversation.connection_generation,
        )
        if self.contexts.get(context.message_id) != context:
            raise AssistantError("assistant_tool_authority_revoked", 403)

    def check_retired_runners(self):
        """Refuse migration while an old scratch runner has unsettled work; preserve every file."""
        import sqlite3

        self.migration_blocked = False
        if not self.settings.app_url:
            return
        namespace = hashlib.sha256(self.settings.app_url.encode()).hexdigest()[:16]
        parent = self.settings.state_root / namespace
        if not parent.is_dir():
            return
        try:
            owners = list(parent.iterdir())
        except OSError:
            self.migration_blocked = True
            return
        for owner in owners:
            if not owner.is_dir():
                continue
            try:
                UUID(owner.name)
            except ValueError:
                continue
            for root in (
                owner / "runner",
                owner / "claude" / "runner",
                owner / "opencode" / "runner",
            ):
                if not root.is_dir():
                    continue
                try:
                    active = any(
                        json.loads(path.read_text(encoding="utf-8")).get("status")
                        in {"prepared", "running"}
                        for path in root.glob("runs/*/record.json")
                    )
                    receipts = (
                        any(root.glob("receipts/*.json"))
                        or any(root.glob("*/*receipt*.json"))
                        or any(root.glob("runs/*/docker-receipts/*.json"))
                    )
                    journal = root / "resume-dispatch.sqlite"
                    if journal.is_file():
                        with sqlite3.connect(
                            journal.as_uri() + "?mode=ro", uri=True
                        ) as connection:
                            active = (
                                active
                                or connection.execute(
                                    "SELECT 1 FROM attempts WHERE state IN ('reserved','running','unknown') LIMIT 1"
                                ).fetchone()
                                is not None
                            )
                    if active or receipts:
                        self.migration_blocked = True
                        return
                except (OSError, ValueError, sqlite3.Error):
                    self.migration_blocked = True
                    return

    def check_connection(self, owner, provider, connection_id, generation):
        """Refuse missing, foreign, revoked or changed bindings without an account fallback."""
        from laomedo.agents.connections.errors import ProviderConnectionError

        if self.migration_blocked:
            raise AssistantError("assistant_reconciliation_required", 409)
        if connection_id is None or generation is None:
            raise AssistantError("assistant_setup_required", 409)
        try:
            if self.provider_connections is None:
                raise ProviderConnectionError("provider_runner_unavailable")
            record = self.provider_connections.admitted(
                owner, connection_id, generation
            )
            if record.provider != provider:
                raise ProviderConnectionError("provider_connection_unavailable")
        except ProviderConnectionError as error:
            raise AssistantError(error.code, 409) from None

    async def connections(self, owner):
        """List safe account rows for this verified profile without starting a runner."""
        from laomedo.agents.connections.errors import ProviderConnectionError

        try:
            if self.provider_connections is None:
                raise ProviderConnectionError("provider_runner_unavailable")
            return {
                "connections": [
                    row.model_dump(mode="json")
                    for row in self.provider_connections.list(owner)
                ]
            }
        except ProviderConnectionError as error:
            raise AssistantError(error.code, 409) from None

    async def host_context(self, token):
        """Resolve an exact private host credential; never accept model-selected identities."""
        context = self.host_tokens.get(token)
        if context is None:
            raise AssistantError("assistant_tool_authority_revoked", 403)
        await self.authorize(context)
        return context

    async def release_idle_session(self, owner, identifier, *, expected=None):
        """Revoke the inactive endpoint and cancel only its exact owned native run."""
        idle = self.idle_tools.get(identifier)
        if (
            idle is None
            or idle.context.owner_id != owner
            or (expected is not None and idle is not expected)
        ):
            return
        self.idle_tools.pop(identifier, None)
        await self._close_tools(
            idle.context, idle.registration, idle.client, idle.token.get_secret_value()
        )
        runner = self.runners.get(
            self._runner_key(
                owner, idle.provider, idle.connection_id, idle.connection_generation
            )
        )
        if runner is not None:
            try:
                await asyncio.to_thread(
                    runner.request, "POST", "/v1/runs/" + idle.run_id + "/cancel", {}
                )
            except AssistantError:
                # Tool authority is already revoked; exact native ownership stays
                # under its independent cleanup path if the gateway is lost.
                pass

    async def lock_session(self, key):
        """Revoke tools immediately and persist the fence before sign-out completes."""
        if not self.store:
            return
        fingerprint = key
        renewal_key = (
            self.provider_connections.resolve_lease(key)
            if self.provider_connections is not None
            else key
        )
        keys = {fingerprint, renewal_key}
        keys.update(self.session_aliases.get(value, value) for value in tuple(keys))
        affected = self._fence_session_contexts(keys)
        renewal_key = renewal_key if renewal_key != fingerprint else None
        try:
            key = await self.store.canonical_session_key(
                fingerprint, renewal_key=renewal_key
            )
            keys.add(key)
            affected.extend(self._fence_session_contexts(keys))
            await self.store.revoke(fingerprint, renewal_key=renewal_key)
        finally:
            for idle in list(self.idle_tools.values()):
                if idle.context.session_key in keys:
                    await self.release_idle_session(
                        idle.context.owner_id, idle.context.conversation_id
                    )
            for context in affected:
                conversation, message = await self.store.message(
                    context.owner_id, context.conversation_id, context.message_id
                )
                runner = self.runners.get(
                    self._runner_key(
                        context.owner_id,
                        conversation.provider,
                        conversation.connection_id,
                        conversation.connection_generation,
                    )
                )
                if runner and message.run_id:
                    try:
                        await asyncio.to_thread(
                            runner.request,
                            "POST",
                            "/v1/runs/" + message.run_id + "/cancel",
                            {},
                        )
                    except AssistantError:
                        pass

    def _fence_session_contexts(self, keys):
        """Remove known browser tool authority synchronously, before storage or cleanup."""
        self.revoked_sessions.update(keys)
        affected = [
            context for context in self.contexts.values() if context.session_key in keys
        ]
        for context in affected:
            self.contexts.pop(context.message_id, None)
        for token, binding in list(self.host_tokens.items()):
            if binding.session_key in keys:
                self.host_tokens.pop(token, None)
        return affected

    @staticmethod
    def _runner_key(owner, provider, connection_id=None, connection_generation=None):
        """Separate every owner, provider, saved account and immutable account epoch."""
        return (owner, provider, connection_id, connection_generation)

    async def runner(
        self, owner, provider="codex", connection_id=None, connection_generation=None
    ):
        """Compose only this owner's dedicated scratch runner, off the app event loop."""
        key = self._runner_key(owner, provider, connection_id, connection_generation)
        lock = self.runner_locks.setdefault(key, asyncio.Lock())
        async with lock:
            value = self.runners.get(key)
            if value is None:
                value = AssistantRunner(
                    self.settings,
                    owner,
                    provider,
                    connection_id,
                    connection_generation,
                    controllers=(
                        self.provider_connections.controllers
                        if self.provider_connections is not None
                        else None
                    ),
                )
                self.runners[key] = value
            return value

    async def models(
        self, owner, provider="codex", connection_id=None, connection_generation=None
    ):
        """Discover actual supported models without submitting a prompt."""
        self.check_connection(owner, provider, connection_id, connection_generation)
        runner = await self.runner(
            owner, provider, connection_id, connection_generation
        )
        cache_key = self._runner_key(
            owner, provider, connection_id, connection_generation
        )
        observed = self.model_catalogs.get(cache_key)
        if observed is not None and observed.runner_instance_id == runner.instance_id:
            return observed.to_payload(provider)
        catalog = await asyncio.to_thread(runner.request, "GET", "/v1/models")
        if not catalog.get("models"):
            raise AssistantError(
                (
                    self.safe_error(catalog.get("error_category"))
                    if catalog.get("error_category")
                    else "assistant_model_unavailable"
                ),
                503,
            )
        from laomedo.agents.agents.base.models import ModelCatalog

        self.check_connection(owner, provider, connection_id, connection_generation)
        observed = ModelCatalogCacheEntry(
            runner_instance_id=runner.instance_id,
            catalog=ModelCatalog.from_payload(catalog),
        )
        self.model_catalogs[cache_key] = observed
        return observed.to_payload(provider)

    async def create(self, owner, key, request):
        """Validate a real model choice and persist an empty conversation without inference."""
        await self.check_session(owner, key)
        catalog = await self.models(
            owner,
            request.provider,
            request.connection_id,
            request.connection_generation,
        )
        selected = next(
            (item for item in catalog["models"] if item["id"] == request.model), None
        )
        if selected is None or request.effort not in selected["efforts"]:
            raise AssistantError("assistant_model_unavailable", 422)
        return await self.store.create(owner, request, session_key=key)

    async def workflow_tools(self, context):
        """Compose the existing workflow owner with authorized installed metadata only."""
        await self.authorize(context)
        catalog = await ComponentCatalog.from_installed(context.owner_id)
        return WorkflowDrafts(self.store, catalog, self.authorize)

    async def save(self, context, workflows, request):
        """Serialize saves and fence new operation keys after an uncertain acknowledgement."""
        lock = self.save_locks.setdefault(context.message_id, asyncio.Lock())
        if lock.locked():
            raise AssistantError("assistant_save_pending")
        digest = hashlib.sha256(
            json.dumps(
                request.model_dump(mode="json"), sort_keys=True, separators=(",", ":")
            ).encode()
        ).hexdigest()
        identity = request.draft_key, digest
        async with lock:
            await self.authorize(context)
            pending = self.uncertain_saves.get(context.message_id)
            if pending is not None and pending != identity:
                raise AssistantError("assistant_save_reconciliation_required")
            try:
                # Same-key reconciliation reads the atomic receipt under the
                # database writer lock before considering any new write.
                result = await workflows.save(context, request)
            except BaseException as error:
                if isinstance(error, asyncio.CancelledError) or (
                    isinstance(error, AssistantError)
                    and error.code == "assistant_save_outcome_unknown"
                ):
                    self.uncertain_saves[context.message_id] = identity
                raise
            self.uncertain_saves.pop(context.message_id, None)
            return result

    async def graph_actions(self, owner):
        """Compose policy-filtered graph actions without a provider runner or model turn."""
        from laomedo.integrations.langflow.assistant.actions import WorkflowActions

        return WorkflowActions(
            self.store, await ComponentCatalog.from_installed(owner), self.authorize
        )

    async def propose_graph_action(self, context, request):
        """Honor existing human conversation consent, never model-selected authority."""
        from laomedo.integrations.langflow.assistant.models import GraphActionDecision

        actions = await self.graph_actions(context.owner_id)
        result = await actions.propose(context, request)
        return await self.decide_graph_action(
            context.owner_id,
            context.session_key,
            context.conversation_id,
            UUID(result["id"]),
            GraphActionDecision(decision="approve", digest=result["digest"]),
            context=context,
        )

    async def decide_graph_action(
        self, owner, key, conversation, identifier, decision, *, context=None
    ):
        """Admit only an authenticated human decision; never let MCP grant this authority."""
        await self.check_session(owner, key)
        actions = await self.graph_actions(owner)
        result, snapshot, actor = await actions.decide(
            owner, key, conversation, identifier, decision, context=context
        )
        if snapshot is not None:
            task = asyncio.create_task(
                actions.execute(result, snapshot, actor, self.check_session)
            )
            self.graph_jobs[identifier] = task
            task.add_done_callback(
                lambda completed: self.graph_jobs.pop(identifier, None)
            )
        return result

    async def skills(self, context, query="", cursor=0):
        """List only the configured imported local registry; private source discovery is not added."""
        if len(query) > 200 or cursor < 0 or cursor > 10000:
            raise AssistantError("assistant_input_invalid", 400)
        await self.authorize(context)
        if (
            self.provider_connections is None
            or self.provider_connections.controllers is None
        ):
            raise AssistantError("assistant_setup_required", 503)
        return await asyncio.to_thread(
            self._skills,
            self.provider_connections.controllers.skill_store,
            query,
            cursor,
        )

    def _skills(self, root, query, cursor):
        """Read bounded immutable registry metadata with the existing integrity verifier."""
        from itertools import islice
        from laomedo.skills.registry.store import SkillStore
        from laomedo.skills.registry.utils.files import is_link
        from laomedo.skills.registry.utils.inspection import inspect_skill

        folder = root / "skills"
        if not folder.is_dir():
            return {"skills": [], "next_cursor": None}
        candidates = list(islice(folder.iterdir(), 513))
        if len(candidates) > 512:
            raise AssistantError("assistant_skill_catalog_unavailable", 503)
        store = SkillStore(root)
        rows = []
        matched = sorted(
            (
                path
                for path in candidates
                if path.is_dir()
                and not is_link(path)
                and query.casefold() in path.name.casefold()
            ),
            key=lambda path: path.name,
        )
        for path in matched[cursor : cursor + 20]:
            revision = store.revision(path.name)
            inspected = inspect_skill(root, path.name, revision["revision_id"])
            skill = next(
                (
                    item.get("content") or item.get("text") or ""
                    for item in inspected["files"]
                    if item.get("path") == "SKILL.md"
                ),
                "",
            )
            match = re.search(
                r"(?m)^description:\s*([^\n]{0,1000})",
                (
                    skill.split("---", 2)[1]
                    if skill.startswith("---") and len(skill.split("---", 2)) > 1
                    else ""
                ),
            )
            rows.append(
                {
                    "skill_id": path.name,
                    "revision_id": revision["revision_id"],
                    "tree_hash": revision["tree_hash"],
                    "description": (
                        match.group(1).strip() if match else "Imported local Skill."
                    ),
                }
            )
        return {
            "skills": rows,
            "next_cursor": cursor + 20 if len(matched) > cursor + 20 else None,
        }

    async def send(self, owner, key, conversation_id, request):
        """Reserve once, then dispatch only a newly admitted message on an app-owned task."""
        await self.check_session(owner, key)
        prior = await self.store.submitted(owner, conversation_id, request)
        if prior is not None:
            return prior
        async with self.store.sessions() as session:
            conversation = await self.store.conversation(
                session, owner, conversation_id
            )
        self.check_connection(
            owner,
            conversation.provider,
            conversation.connection_id,
            conversation.connection_generation,
        )
        if request.initial_native_command is not None and (
            conversation.provider != "codex" or conversation.run_id is not None
        ):
            raise AssistantError("native_command_context_invalid", 409)
        if request.model is not None:
            catalog = await self.models(
                owner,
                conversation.provider,
                conversation.connection_id,
                conversation.connection_generation,
            )
            choice = next(
                (item for item in catalog["models"] if item["id"] == request.model),
                None,
            )
            if choice is None or request.effort not in choice["efforts"]:
                raise AssistantError("assistant_model_unavailable", 422)
        if (
            len(self.jobs) >= self.settings.max_active_turns
            and conversation_id not in self.jobs
        ):
            raise AssistantError("assistant_capacity_busy", 409)
        runner = await self.runner(
            owner,
            conversation.provider,
            conversation.connection_id,
            conversation.connection_generation,
        )
        async with self.store.sessions() as session:
            conversation = await self.store.conversation(
                session, owner, conversation_id
            )
        if (
            conversation.runner_instance_id
            and conversation.runner_instance_id != runner.instance_id
            and not (
                conversation.active_message_id is None
                and await self.store.completed_binding(owner, conversation_id)
            )
        ):
            if conversation.active_message_id:
                await self.reconcile(owner, conversation_id)
            else:
                await self.store.block(
                    owner, conversation_id, "assistant_runner_restarted"
                )
            raise AssistantError("assistant_runner_restarted", 409)
        message, created = await self.store.reserve(
            owner, conversation_id, request, session_key=key
        )
        if created:
            self.dispatch_reserved(owner, key, conversation_id, message)
        return message

    def dispatch_reserved(self, owner, key, conversation_id, message):
        """Schedule exactly one already-committed chat or approved-command reservation."""
        context = AuthoringContext(
            owner_id=owner,
            conversation_id=conversation_id,
            message_id=message["id"],
            attempt_id=message["attempt_id"],
            session_key=key,
        )
        self.contexts[context.message_id] = context
        task = asyncio.create_task(
            self._job(context), name="laomedo-assistant-" + str(context.message_id)
        )
        self.jobs[conversation_id] = task
        task.add_done_callback(
            lambda finished: self._job_done(conversation_id, finished)
        )

    async def native_catalog(self, owner, conversation_id):
        """Project commands only from the current conversation's existing native session."""
        from laomedo.agents.agents.base.models import NativeCommandDiscovery
        from pydantic import ValidationError

        async with self.store.sessions() as session:
            conversation = await self.store.conversation(
                session, owner, conversation_id
            )
        if not conversation.run_id:
            return {
                "state": "unavailable",
                "reason": "native_session_not_created",
                "commands": [],
            }
        runner = await self.runner(
            owner,
            conversation.provider,
            conversation.connection_id,
            conversation.connection_generation,
        )
        record = await asyncio.to_thread(
            runner.request, "GET", "/v1/runs/" + conversation.run_id
        )
        observed = record.get("native_commands") or {}
        thread = record.get("thread_id")
        if (
            not thread
            or observed.get("thread_id") != thread
            or (conversation.thread_id and conversation.thread_id != thread)
        ):
            return {
                "state": "unavailable",
                "reason": "native_session_not_observed",
                "commands": [],
            }
        if observed.get("catalog") is None:
            return {
                "state": "unavailable",
                "reason": "native_catalog_not_observed",
                "commands": [],
            }
        try:
            result = NativeCommandDiscovery.model_validate(
                observed.get("projection")
            ).model_dump(mode="json")
        except ValidationError:
            return {
                "state": "unavailable",
                "reason": "native_catalog_invalid",
                "commands": [],
            }
        return {**result, "run_id": conversation.run_id, "thread_id": thread}

    async def submit_native_command(self, owner, key, conversation_id, request):
        """Admit explicit human slash input using existing capacity and command dispatch."""
        from laomedo.integrations.langflow.assistant.native import NativeCommands

        await self.check_session(owner, key)
        if self.closing or (
            len(self.jobs) >= self.settings.max_active_turns
            and conversation_id not in self.jobs
        ):
            raise AssistantError("assistant_capacity_busy", 409)
        result, reserved = await NativeCommands(self).submit(
            owner, key, conversation_id, request
        )
        if reserved is not None:
            self.dispatch_reserved(owner, key, conversation_id, reserved)
        return result

    async def decide_native_action(
        self, owner, key, conversation_id, identifier, decision
    ):
        """Use human app authority to reserve an exact command, then schedule it once."""
        from laomedo.integrations.langflow.assistant.native import NativeCommands

        await self.check_session(owner, key)
        if self.closing or (
            len(self.jobs) >= self.settings.max_active_turns
            and conversation_id not in self.jobs
        ):
            raise AssistantError("assistant_capacity_busy", 409)
        result, reserved = await NativeCommands(self).decide(
            owner, key, conversation_id, identifier, decision
        )
        if reserved is not None:
            self.dispatch_reserved(owner, key, conversation_id, reserved)
        return result

    def _job_done(self, identifier, task):
        """Release this task's slot and consume errors; retained reservations remain reconcile-only."""
        if self.jobs.get(identifier) is task:
            self.jobs.pop(identifier, None)
        if not task.cancelled():
            task.exception()

    def safe_error(self, code):
        """Keep known machine categories; never release arbitrary native exception text."""
        return (
            code
            if code in RUNNER_FAILURE_CODES or code in MCP_ERROR_CODES
            else "assistant_turn_failed"
        )

    async def _reap_idle_tools(self):
        """Release inactive transports after account removal or native idle cleanup."""
        while not self.closing:
            await asyncio.sleep(1)
            for identifier, idle in list(self.idle_tools.items()):
                release = False
                try:
                    self.check_connection(
                        idle.context.owner_id,
                        idle.provider,
                        idle.connection_id,
                        idle.connection_generation,
                    )
                    runner = self.runners.get(
                        self._runner_key(
                            idle.context.owner_id,
                            idle.provider,
                            idle.connection_id,
                            idle.connection_generation,
                        )
                    )
                    release = runner is None or not await asyncio.to_thread(
                        runner.has_live_session, idle.run_id
                    )
                except AssistantError:
                    release = True
                if release:
                    await self.release_idle_session(
                        idle.context.owner_id, identifier, expected=idle
                    )

    async def _close_tools(self, context, registration, client, token, *, retain=False):
        """Revoke first, then drain actual host tool tasks before permitting another message."""
        self.contexts.pop(context.message_id, None)
        if self.host_tokens.get(token) is context:
            self.host_tokens.pop(token, None)
        if retain and registration is not None:
            conversation, message = await self.store.message(
                context.owner_id, context.conversation_id, context.message_id
            )
            if not message.run_id:
                raise AssistantError("assistant_native_identity_mismatch", 409)
            self.idle_tools[context.conversation_id] = IdleAssistantTools(
                provider=conversation.provider,
                connection_id=conversation.connection_id,
                connection_generation=conversation.connection_generation,
                run_id=message.run_id,
                context=context,
                registration=registration,
                client=client,
                token=token,
            )
        elif registration is not None:
            McpRegistry.current().release(str(registration.registration_id))
        tasks = list(self.tool_tasks.pop(context.message_id, set()))
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=15
            )
        if client and not retain:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=10)
            except Exception:
                pass  # Authority is already revoked; an idle session is not an agent grant.
        self.save_locks.pop(context.message_id, None)
        claimed = self.claimed_idle_tools.pop(context.message_id, None)
        if claimed is not None and not retain:
            # A stopped or refused first dispatch must not leave a native
            # controller attached to the endpoint just released above.
            runner = self.runners.get(
                self._runner_key(
                    context.owner_id,
                    claimed.provider,
                    claimed.connection_id,
                    claimed.connection_generation,
                )
            )
            if runner is not None:
                try:
                    await asyncio.to_thread(
                        runner.request,
                        "POST",
                        "/v1/runs/" + claimed.run_id + "/cancel",
                        {},
                    )
                except AssistantError:
                    # Revocation is complete; native cleanup remains uncertain
                    # and is independently reconciled by the owning runner.
                    pass

    async def _job(self, context):
        """Use existing asynchronous start/resume once, then observe the exact attempt."""
        from lfx.base.mcp.util import MCPStreamableHttpClient, update_tools

        registration = client = None
        token = secrets.token_urlsafe(32)
        dispatched = False
        try:
            await self.authorize(context)
            conversation, message = await self.store.message(
                context.owner_id, context.conversation_id, context.message_id
            )
            runner = await self.runner(
                context.owner_id,
                conversation.provider,
                conversation.connection_id,
                conversation.connection_generation,
            )
            self.host_tokens[token] = context
            idle = self.idle_tools.pop(context.conversation_id, None)
            if idle is not None:
                self.host_tokens.pop(token, None)
                if not idle.matches(context):
                    self.idle_tools[context.conversation_id] = idle
                    await self.release_idle_session(
                        context.owner_id, context.conversation_id
                    )
                    raise AssistantError("assistant_native_identity_mismatch", 409)
                registration, client, token = (
                    idle.registration,
                    idle.client,
                    idle.token.get_secret_value(),
                )
                self.claimed_idle_tools[context.message_id] = idle
                self.host_tokens[token] = context
            else:
                client = MCPStreamableHttpClient()
                client.set_session_context("assistant:" + str(context.message_id))
                _, tools, _ = await update_tools(
                    AUTHORING_SERVER_NAME,
                    {
                        "mode": "Streamable_HTTP",
                        "url": self.settings.app_url + "/api/v1/laomedo/assistant/mcp/",
                        "headers": {"Authorization": "Bearer " + token},
                    },
                    mcp_streamable_http_client=client,
                    current_user_id=context.owner_id,
                )
                if len(tools) != len(AUTHORING_TOOL_NAMES):
                    raise AssistantError("assistant_tool_catalog_changed", 503)
                admitted_tools = [LangflowMcpTool(tool) for tool in tools]
                if conversation.run_id:
                    from laomedo.agents.mcp.models import McpManifest

                    record = await asyncio.to_thread(
                        runner.request, "GET", "/v1/runs/" + conversation.run_id
                    )
                    if not record.get("mcp_manifest"):
                        raise AssistantError("assistant_tool_catalog_changed", 409)
                    frozen = McpManifest.model_validate(record["mcp_manifest"])
                    selected = {
                        (item.server, item.upstream_name) for item in frozen.tools
                    }
                    admitted_tools = [
                        tool
                        for tool in admitted_tools
                        if (tool.descriptor.server, tool.descriptor.upstream_name)
                        in selected
                    ]
                    if (
                        McpManifest(
                            tools=tuple(tool.descriptor for tool in admitted_tools)
                        )
                        != frozen
                    ):
                        raise AssistantError("assistant_tool_catalog_changed", 409)
                registration = await McpRegistry.current().register(admitted_tools)
            await self.authorize(context)
            _, current = await self.store.message(
                context.owner_id, context.conversation_id, context.message_id
            )
            if current.stop_requested:
                raise AssistantError("assistant_cancelled_before_dispatch")
            payload = {
                "task": ASSISTANT_INSTRUCTIONS + "\nUser message:\n" + message.text,
                "model": message.model or conversation.model,
                "effort": message.effort or conversation.effort,
                "mcp_manifest": registration.manifest.model_dump(mode="json"),
                "mcp_registration": str(registration.registration_id),
            }
            if message.initial_native_command is not None:
                if (
                    message.initial_native_command != "status"
                    or message.text != "/status"
                    or conversation.provider != "codex"
                    or conversation.run_id is not None
                    or message.native_action_id is not None
                ):
                    raise AssistantError("native_command_context_invalid", 409)
                payload["task"] = "/status"
                payload["initial_native_command"] = "status"
            if message.native_action_id is not None:
                from laomedo.integrations.langflow.assistant.models import (
                    AssistantNativeAction,
                    NativeCommandRequest,
                )

                async with self.store.sessions() as session:
                    action = await session.get(
                        AssistantNativeAction, message.native_action_id
                    )
                    if (
                        action is None
                        or action.owner_id != context.owner_id
                        or action.conversation_id != context.conversation_id
                        or action.session_key != context.session_key
                        or action.state != "executing"
                        or action.result_message_id != message.id
                        or action.run_id != conversation.run_id
                        or action.thread_id != conversation.thread_id
                    ):
                        raise AssistantError("assistant_tool_authority_revoked", 403)
                    command = NativeCommandRequest.model_validate(action.request)
                    if command.text() != message.text:
                        raise AssistantError("assistant_native_identity_mismatch", 409)
                payload["task"] = command.text()
                payload["native_command"] = command.model_dump(
                    mode="json", exclude={"operation_key"}
                )
            if conversation.run_id:
                payload.update(
                    activity_attempt_id=str(context.attempt_id),
                    expected_thread_id=conversation.thread_id,
                    expected_post_run_hash=conversation.workspace_hash,
                )
                path = "/v1/runs/" + conversation.run_id + "/resume/async"
            else:
                payload["request_id"] = str(message.id)
                path = "/v1/runs/async"
            dispatched = True
            record = await asyncio.to_thread(runner.request, "POST", path, payload)
            run_id = conversation.run_id or record["run_id"]
            native_attempt = (
                str(context.attempt_id)
                if conversation.run_id
                else record.get("activity_initial_attempt_id")
                or record.get("activity_attempt_id")
            )
            if not native_attempt:
                raise AssistantError("assistant_native_identity_mismatch")
            if conversation.run_id:
                if record.get("runner_instance_id") != runner.instance_id:
                    raise AssistantError("assistant_runner_restarted")
                await self.store.rebind_completed(
                    context.owner_id,
                    context.conversation_id,
                    context.message_id,
                    runner.instance_id,
                )
            await self.store.observe(
                context.owner_id,
                context.conversation_id,
                context.message_id,
                run_id=run_id,
                native_attempt_id=native_attempt,
                instance_id=runner.instance_id,
                state="running",
            )
            while True:
                await self.authorize(context)
                if await self.reconcile(
                    context.owner_id, context.conversation_id, defer_settlement=True
                ):
                    break
                await asyncio.sleep(0.5)
            observed = await asyncio.to_thread(
                runner.request, "GET", "/v1/runs/" + run_id
            )
            retain = (
                observed.get("live_session") == "idle"
                and observed.get("controller_cleanup") == "retained"
                and not observed.get("turns")
            )
            await self._close_tools(context, registration, client, token, retain=retain)
            registration = client = None
            await self.reconcile(context.owner_id, context.conversation_id)
        except asyncio.CancelledError:
            await self._mark_unknown(context, "assistant_dispatch_unknown")
            raise
        except Exception as error:
            logging.getLogger(__name__).warning(
                "assistant_turn_observation_failed type=%s frames=%s",
                type(error).__name__,
                [
                    (Path(frame.filename).name, frame.name, frame.lineno)
                    for frame in traceback.extract_tb(error.__traceback__)
                ],
            )
            if dispatched:
                await self._mark_unknown(
                    context,
                    (
                        error.code
                        if isinstance(error, AssistantError)
                        and error.code.startswith("assistant_")
                        else "assistant_dispatch_unknown"
                    ),
                )
            else:
                try:
                    await self._close_tools(context, registration, client, token)
                except Exception:
                    await self._mark_unknown(
                        context, "assistant_tool_settlement_unknown"
                    )
                    return
                registration = client = None
                conversation, message = await self.store.message(
                    context.owner_id, context.conversation_id, context.message_id
                )
                await self.store.observe(
                    context.owner_id,
                    context.conversation_id,
                    context.message_id,
                    state="cancelled" if message.stop_requested else "failed",
                    error=(
                        error.code
                        if isinstance(error, AssistantError)
                        else "assistant_tool_unavailable"
                    ),
                    settled=True,
                    thread_id=conversation.thread_id,
                    workspace_hash=conversation.workspace_hash,
                )
        finally:
            try:
                await self._close_tools(context, registration, client, token)
            except Exception:
                await self._mark_unknown(context, "assistant_tool_settlement_unknown")

    async def _mark_unknown(self, context, code):
        """Keep an uncertain attempt reserved and its identity available for lookup."""
        try:
            await self.store.observe(
                context.owner_id,
                context.conversation_id,
                context.message_id,
                state="unknown",
                error=code,
                reconciled=True,
            )
        except Exception:
            pass  # Durable reservation remains; no exception may trigger a replay.

    async def reconcile(self, owner, identifier, *, defer_settlement=False):
        """Inspect retained runner identities only; this method never submits a prompt."""
        async with self.store.sessions() as session:
            conversation = await self.store.conversation(session, owner, identifier)
        if conversation.active_message_id is None:
            return True
        conversation, message = await self.store.message(
            owner, identifier, conversation.active_message_id
        )
        runner = await self.runner(
            owner,
            conversation.provider,
            conversation.connection_id,
            conversation.connection_generation,
        )
        if (
            conversation.runner_instance_id
            and conversation.runner_instance_id != runner.instance_id
        ):
            await self.store.observe(
                owner,
                identifier,
                message.id,
                instance_id=runner.instance_id,
                state="unknown",
                error="assistant_runner_restarted",
                settled=True,
                reconciled=True,
            )
            return True
        try:
            if message.run_id or conversation.run_id:
                record = await asyncio.to_thread(
                    runner.request,
                    "GET",
                    "/v1/runs/" + (message.run_id or conversation.run_id),
                )
            else:
                record = await asyncio.to_thread(
                    runner.request, "GET", "/v1/requests/" + str(message.id)
                )
        except AssistantError:
            return False
        native_attempt = message.native_attempt_id or (
            str(message.attempt_id)
            if conversation.run_id and not message.run_id
            else record.get("activity_initial_attempt_id")
        )
        if not native_attempt:
            return False
        dispatch = None
        if native_attempt == str(message.attempt_id):
            try:
                dispatch = await asyncio.to_thread(
                    runner.request,
                    "GET",
                    "/v1/runs/" + record["run_id"] + "/resume/" + native_attempt,
                )
            except AssistantError:
                return False
        observed_instance = (
            dispatch.get("runner_instance_id")
            if dispatch is not None
            else record.get("runner_instance_id")
        )
        if observed_instance != runner.instance_id:
            await self.store.observe(
                owner,
                identifier,
                message.id,
                run_id=record["run_id"],
                native_attempt_id=native_attempt,
                instance_id=runner.instance_id,
                state="unknown",
                settled=True,
                reconciled=True,
                error="assistant_runner_restarted",
            )
            return True
        await self.store.observe(
            owner,
            identifier,
            message.id,
            run_id=record["run_id"],
            native_attempt_id=native_attempt,
            instance_id=runner.instance_id,
        )
        never_started = (
            record.get("status") == "cancelled"
            and record.get("cancel_confirmed") is True
            and record.get("attempt_finished") is True
            and record.get("activity_initial_attempt_id") == native_attempt
            and not record.get("activity_attempt_id")
            and not record.get("container_ownership")
        )
        if record.get("activity_attempt_id") != native_attempt and not never_started:
            if native_attempt == str(message.attempt_id):
                if dispatch.get("status") == "failed":
                    if defer_settlement:
                        return True
                    if message.id in self.contexts:
                        return False
                    code = self.safe_error(dispatch.get("error_category"))
                    await self.store.receipt_barrier(owner, identifier, message.id)
                    self.uncertain_saves.pop(message.id, None)
                    await self.store.observe(
                        owner,
                        identifier,
                        message.id,
                        state="failed",
                        settled=True,
                        reconciled=True,
                        error=code,
                        thread_id=(
                            conversation.thread_id if code == "runner_busy" else None
                        ),
                        workspace_hash=(
                            conversation.workspace_hash
                            if code == "runner_busy"
                            else None
                        ),
                    )
                    return True
            return False
        if message.stop_requested and record.get("status") in {"prepared", "running"}:
            await asyncio.to_thread(
                runner.request, "POST", "/v1/runs/" + record["run_id"] + "/cancel", {}
            )
        if not never_started:
            try:
                activity = await asyncio.to_thread(
                    runner.request,
                    "GET",
                    "/v1/runs/"
                    + record["run_id"]
                    + "/activity?attempt="
                    + native_attempt
                    + "&after=0&limit=200",
                )
                await self.store.cache_activity(owner, identifier, message.id, activity)
            except AssistantError:
                pass  # Retain the previous normalized view; do not invent content.
        if not record.get("attempt_finished") or not runner.is_settled(
            record["run_id"]
        ):
            return False
        status = record.get("status")
        if status not in {"completed", "cancelled", "failed", "interrupted", "unknown"}:
            return False
        not_launched = (
            record.get("controller_cleanup") == "not_started"
            and record.get("container_ownership", {}).get("cleanup_detail")
            == "not_launched"
        )
        retained_control = (
            status == "completed"
            and record.get("live_session") == "idle"
            and record.get("controller_cleanup") == "retained"
            and not record.get("turns")
            and any(
                receipt.get("attempt_id") == native_attempt
                and receipt.get("status") == "completed"
                and (receipt.get("request") or {}).get("name")
                in {"status", "mcp", "skills"}
                for receipt in record.get("native_command_receipts", [])
            )
            and runner.has_live_session(record["run_id"])
        )
        # OpenCode confirms its entire owned controller/worker cleanup in this
        # terminal field. Unlike Codex/Claude it has no single-controller
        # container_ownership receipt; requiring that absent receipt strands
        # even a successfully completed and fully cleaned-up invocation.
        cleanup_verified = (
            record.get("provider") == "opencode"
            and record.get("controller_cleanup") == "confirmed"
        ) or record.get("container_ownership", {}).get("cleanup_verified") is True
        if (
            not never_started
            and not retained_control
            and (
                (record.get("controller_cleanup") != "confirmed" and not not_launched)
                or not cleanup_verified
            )
        ):
            await self.store.observe(
                owner,
                identifier,
                message.id,
                state="unknown",
                error="assistant_cleanup_unverified",
                reconciled=True,
            )
            return False
        if defer_settlement:
            return True
        if message.id in self.contexts:
            return False  # Only the job may unlock Send after its tool tasks drain.
        await self.store.receipt_barrier(owner, identifier, message.id)
        self.uncertain_saves.pop(message.id, None)
        checkpoint = record.get("resume_checkpoint") or {}
        digest = (
            record.get("post_run_hash")
            if status == "completed"
            else checkpoint.get("workspace_hash")
        )
        if status != "completed" and (
            checkpoint.get("attempt_id") != native_attempt
            or checkpoint.get("runner_instance_id") != runner.instance_id
            or checkpoint.get("thread_id") != record.get("thread_id")
        ):
            digest = None
        await self.store.observe(
            owner,
            identifier,
            message.id,
            state=status,
            response=(
                record.get("answer") if isinstance(record.get("answer"), str) else None
            ),
            error=(
                self.safe_error(record.get("error_category"))
                if record.get("error_category")
                else None
            ),
            thread_id=record.get("thread_id"),
            workspace_hash=digest,
            settled=True,
            reconciled=True,
        )
        return True

    async def activity(self, owner, identifier, attempt, after):
        """Map an owner-scoped application attempt to its observed native Activity page."""
        from laomedo.integrations.langflow.assistant.models import AssistantMessage

        async with self.store.sessions() as session:
            conversation = await self.store.conversation(session, owner, identifier)
            row = (
                await session.exec(
                    select(AssistantMessage).where(
                        AssistantMessage.conversation_id == identifier,
                        AssistantMessage.attempt_id == attempt,
                    )
                )
            ).first()
            message = row.model_dump(mode="json") if row else None
            settled = row is not None and conversation.active_message_id != row.id
        if message is None:
            raise AssistantError("assistant_message_not_found", 404)
        if (
            settled
            and message.get("activity_snapshot")
            and (
                after < message["activity_snapshot"]["next_after"]
                or not message["activity_snapshot"]["has_more"]
            )
        ):
            snapshot = dict(message["activity_snapshot"])
            snapshot["records"] = [
                row for row in snapshot["records"] if row["sequence"] > after
            ]
            snapshot["next_after"] = max(after, snapshot["next_after"])
            return snapshot
        if not message["run_id"] or not message["native_attempt_id"]:
            return {
                "available": False,
                "reason": "starting",
                "records": [],
                "next_after": after,
                "has_more": False,
                "closed": False,
                "complete": None,
                "projection": None,
            }
        try:
            runner = await self.runner(
                owner,
                conversation.provider,
                conversation.connection_id,
                conversation.connection_generation,
            )
            return await asyncio.to_thread(
                runner.request,
                "GET",
                "/v1/runs/"
                + message["run_id"]
                + "/activity?attempt="
                + message["native_attempt_id"]
                + "&after="
                + str(after)
                + "&limit=100",
            )
        except AssistantError:
            if not message.get("activity_snapshot"):
                raise
            snapshot = dict(message["activity_snapshot"])
            snapshot.update(
                records=[],
                next_after=max(after, snapshot["next_after"]),
                has_more=False,
                complete=False,
                reason="activity_journal_unavailable",
            )
            return snapshot

    async def stop(self, owner, identifier, attempt):
        """Stop only the current exact application attempt; acknowledgement is not settlement."""
        async with self.store.sessions() as session:
            conversation = await self.store.conversation(session, owner, identifier)
        if conversation.active_message_id is None:
            return {"state": conversation.state}
        _, message = await self.store.message(
            owner, identifier, conversation.active_message_id
        )
        if message.attempt_id != attempt:
            raise AssistantError("assistant_native_identity_mismatch")
        await self.store.request_stop(owner, identifier, attempt)
        context = self.contexts.get(message.id)
        if context:
            for token, binding in list(self.host_tokens.items()):
                if binding == context:
                    self.host_tokens.pop(token, None)
        if message.run_id:
            runner = await self.runner(
                owner,
                conversation.provider,
                conversation.connection_id,
                conversation.connection_generation,
            )
            await asyncio.to_thread(
                runner.request, "POST", "/v1/runs/" + message.run_id + "/cancel", {}
            )
        return {"state": "stopping"}

    async def detail(self, owner, identifier, cursor=0):
        """Reopen retained history without replay; reconcile before exposing Send."""
        detail = await self.store.detail(owner, identifier, cursor)
        conversation = detail["conversation"]
        try:
            if conversation["active_message_id"] and identifier not in self.jobs:
                if not await self.reconcile(owner, identifier):
                    await self.store.observe(
                        owner,
                        identifier,
                        UUID(conversation["active_message_id"]),
                        state="unknown",
                        error="assistant_dispatch_unknown",
                        reconciled=True,
                    )
            elif conversation["run_id"] and not conversation["active_message_id"]:
                runner = await self.runner(
                    owner,
                    conversation["provider"],
                    (
                        UUID(conversation["connection_id"])
                        if conversation.get("connection_id")
                        else None
                    ),
                    conversation.get("connection_generation"),
                )
                if conversation[
                    "runner_instance_id"
                ] != runner.instance_id and not await self.store.completed_binding(
                    owner, identifier
                ):
                    await self.store.block(
                        owner, identifier, "assistant_runner_restarted"
                    )
            return await self.store.detail(owner, identifier, cursor)
        except Exception:
            detail["observation_error"] = "assistant_runner_unavailable"
            return detail
