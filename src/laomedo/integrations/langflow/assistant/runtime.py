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
    AuthoringContext,
    AssistantSession,
)
from laomedo.integrations.langflow.assistant.persistence import AssistantStore
from laomedo.integrations.langflow.assistant.runner import AssistantRunner
from laomedo.integrations.langflow.assistant.settings import (
    AUTHORING_SERVER_NAME,
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
        self.store = self.mcp = self.upstream = None
        self.runners, self.runner_locks, self.jobs = {}, {}, {}
        self.contexts, self.host_tokens, self.tool_tasks = {}, {}, {}
        self.save_locks, self.uncertain_saves = {}, {}
        self.graph_jobs = {}
        self.revoked_sessions = set()
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
        if owner.settings.app_url and owner.settings.runner_service_file:
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
            if self.mcp is None:
                yield state
                return
            await self.store.initialize()
            async with self.mcp.server.session_manager.run():
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
                    yield state
                finally:
                    self.closing = True
                    self.ready = False
                    self.host_tokens.clear()
                    cancellations = []
                    for conversation in await self.store.pending():
                        runner = self.runners.get(conversation.owner_id)
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
        key = hashlib.sha256(token.encode()).hexdigest()
        await self.store.admit_session(key, UUID(str(user.id)), expires)
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
        if self.contexts.get(context.message_id) != context:
            raise AssistantError("assistant_tool_authority_revoked", 403)

    async def host_context(self, token):
        """Resolve an exact private host credential; never accept model-selected identities."""
        context = self.host_tokens.get(token)
        if context is None:
            raise AssistantError("assistant_tool_authority_revoked", 403)
        await self.authorize(context)
        return context

    async def lock_session(self, key):
        """Revoke tools immediately and persist the fence before sign-out completes."""
        if not self.store:
            return
        self.revoked_sessions.add(key)
        affected = [
            context for context in self.contexts.values() if context.session_key == key
        ]
        for context in affected:
            self.contexts.pop(context.message_id, None)
            for token, binding in list(self.host_tokens.items()):
                if binding == context:
                    self.host_tokens.pop(token, None)
            runner = self.runners.get(context.owner_id)
            conversation, message = await self.store.message(
                context.owner_id, context.conversation_id, context.message_id
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
        await self.store.revoke(key)

    async def runner(self, owner):
        """Compose only this owner's dedicated scratch runner, off the app event loop."""
        lock = self.runner_locks.setdefault(owner, asyncio.Lock())
        async with lock:
            value = self.runners.get(owner)
            if value is None:
                value = AssistantRunner(self.settings, owner)
                from laomedo.agents.errors import RunnerError
                from laomedo.host.private_state.errors import PrivateStateError

                try:
                    await asyncio.to_thread(value.start)
                except (RunnerError, PrivateStateError) as error:
                    raise AssistantError(error.code, 503) from None
                except (OSError, ValueError):
                    raise AssistantError("assistant_setup_required", 503) from None
                self.runners[owner] = value
            return value

    async def models(self, owner):
        """Discover actual supported models without submitting a prompt."""
        runner = await self.runner(owner)
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
        return {
            "provider": "codex",
            "models": [
                {"id": item["id"], "efforts": item.get("efforts", [])}
                for item in catalog.get("models", [])[:100]
            ],
        }

    async def create(self, owner, key, request):
        """Validate a real model choice and persist an empty conversation without inference."""
        await self.check_session(owner, key)
        catalog = await self.models(owner)
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

    async def decide_graph_action(self, owner, key, conversation, identifier, decision):
        """Admit only an authenticated human decision; never let MCP grant this authority."""
        await self.check_session(owner, key)
        actions = await self.graph_actions(owner)
        result, snapshot, actor = await actions.decide(
            owner, key, conversation, identifier, decision
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
        from laomedo.host.runner.service import RunnerService

        config = await asyncio.to_thread(
            RunnerService(self.settings.runner_service_file).config
        )
        return await asyncio.to_thread(
            self._skills, Path(config["skill_store"]), query, cursor
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
        if request.model is not None:
            catalog = await self.models(owner)
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
        runner = await self.runner(owner)
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
        return message

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

    async def _close_tools(self, context, registration, client, token):
        """Revoke first, then drain actual host tool tasks before permitting another message."""
        self.contexts.pop(context.message_id, None)
        self.host_tokens.pop(token, None)
        if registration is not None:
            McpRegistry.current().release(str(registration.registration_id))
        tasks = list(self.tool_tasks.pop(context.message_id, set()))
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.wait_for(
                asyncio.gather(*tasks, return_exceptions=True), timeout=15
            )
        if client:
            try:
                await asyncio.wait_for(client.disconnect(), timeout=10)
            except Exception:
                pass  # Authority is already revoked; an idle session is not an agent grant.
        self.save_locks.pop(context.message_id, None)

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
            runner = await self.runner(context.owner_id)
            self.host_tokens[token] = context
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
            if len(tools) != 6:
                raise AssistantError("assistant_tool_catalog_changed", 503)
            registration = await McpRegistry.current().register(
                [LangflowMcpTool(tool) for tool in tools]
            )
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
            await self._close_tools(context, registration, client, token)
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
        runner = await self.runner(owner)
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
            if message.run_id:
                record = await asyncio.to_thread(
                    runner.request, "GET", "/v1/runs/" + message.run_id
                )
            else:
                record = await asyncio.to_thread(
                    runner.request, "GET", "/v1/requests/" + str(message.id)
                )
        except AssistantError:
            return False
        native_attempt = message.native_attempt_id or record.get(
            "activity_initial_attempt_id"
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
                    + "&after=0&limit=500",
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
        if not never_started and (
            (record.get("controller_cleanup") != "confirmed" and not not_launched)
            or record.get("container_ownership", {}).get("cleanup_verified") is not True
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
            runner = await self.runner(owner)
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
            runner = await self.runner(owner)
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
                runner = await self.runner(owner)
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
