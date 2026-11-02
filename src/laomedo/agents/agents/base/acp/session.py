"""Provider-neutral ACP lifecycle using the upstream Python SDK."""

import asyncio
import time

from acp import RequestError, connect_to_agent
from acp.schema import (
    ClientCapabilities,
    DeniedOutcome,
    Implementation,
    RequestPermissionResponse,
    TextContentBlock,
)

from laomedo.agents.agents.base.acp.models import AcpTurn
from laomedo.agents.agents.base.acp.transport import DockerTransport
from laomedo.agents.errors import RunnerError


class AcpSession:
    """Communicate with any ACP agent; provider policy stays in its launch config.

    Parameters
    ----------
    session : py_docker.sessions.session.Session
        Session created on this thread. Close removes its exact owned container.
    on_update : callable or None
        Persist observed session updates; capture completeness belongs to its owner.
    on_extension : callable or None
        Optional provider telemetry extension receiver, never a tool executor.
    on_precheck : callable or None
        Pure output-contract validator for the one allowlisted request extension.

    The client advertises no host filesystem or terminal capabilities. It denies
    every permission request and implements no host execution callbacks. Its only
    optional request extension performs pure output-contract validation. Tool
    access must be configured explicitly in the controller and its MCP server.
    """

    def __init__(self, session, *, on_update=None, on_extension=None, on_precheck=None):
        """Connect the SDK to one session on the current asyncio event loop."""
        self.session = session
        self.on_update = on_update
        self.on_extension = on_extension
        self.on_precheck = on_precheck
        self.updates = []
        self.session_id = None
        self.capabilities = None
        self.cancel_sent = False
        self.protocol_failed = False
        self.connection = connect_to_agent(
            self, DockerTransport(session, on_failure=self._fail_protocol)
        )

    def _fail_protocol(self):
        """Invalidate success without exposing an SDK diagnostic traceback."""
        self.protocol_failed = True

    async def initialize(self):
        """Negotiate ACP v1 without logging authentication or native payloads."""
        reply = await self._request(
            self.connection.initialize(
                protocol_version=1,
                client_capabilities=ClientCapabilities(),
                client_info=Implementation(name="laomedo", version="0.1.0"),
            ),
            "initialize",
            45,
        )
        if reply.protocol_version != 1:
            raise RunnerError("runner_transport_failed")
        self.capabilities = reply.agent_capabilities
        return reply

    async def open(
        self, *, cwd="/draft", session_id=None, mcp_servers=(), metadata=None
    ):
        """Create or load the actual persisted agent session, without a model turn.

        A resume uses loadSession only when the agent advertises support. Failure
        never falls back to creating a fresh session or dispatching another turn.
        """
        arguments = {"cwd": cwd, "mcp_servers": list(mcp_servers), **(metadata or {})}
        if session_id is None:
            reply = await self._request(
                self.connection.new_session(**arguments), "session/new", 60
            )
            self.session_id = reply.session_id
        else:
            if self.capabilities is None or not self.capabilities.load_session:
                raise RunnerError("resume_provider_binding_mismatch")
            reply = await self._request(
                self.connection.load_session(session_id=session_id, **arguments),
                "session/load",
                60,
            )
            self.session_id = session_id
        self.updates.clear()  # Replayed history belongs to the earlier prompt.
        return reply

    async def configure(self, config_id: str, value: str):
        """Set an advertised option and return the agent's observed config state."""
        return await self._request(
            self.connection.set_config_option(
                session_id=self.session_id, config_id=config_id, value=value
            ),
            "session/set_config_option",
            30,
        )

    async def prompt(
        self, text: str, *, cancelled, seconds: float, metadata=None, check_health=None
    ) -> AcpTurn:
        """Await a terminal response, forwarding cancellation within 100 ms.

        Cancellation and timeout have a five-second protocol grace period. The
        caller must close this session before trusting descendant cleanup. A
        transport failure never implies a confirmed remote completion.
        """
        if self.session_id is None:
            raise RunnerError("runner_transport_failed")
        self.updates.clear()
        self.cancel_sent = False
        deadline = time.monotonic() + seconds
        pending = asyncio.create_task(
            self.connection.prompt(
                session_id=self.session_id,
                prompt=[TextContentBlock(type="text", text=text)],
                **(metadata or {}),
            )
        )
        timed_out = False
        health_error = None
        next_health = 0.0
        try:
            while not pending.done():
                if (
                    check_health is not None
                    and not self.cancel_sent
                    and not cancelled.is_set()
                    and time.monotonic() >= next_health
                ):
                    try:
                        check_health()
                    except RunnerError as failure:
                        health_error = failure
                    except Exception:
                        health_error = RunnerError("runner_transport_failed")
                    next_health = time.monotonic() + 0.25
                if not self.cancel_sent and (
                    cancelled.is_set()
                    or time.monotonic() >= deadline
                    or health_error is not None
                ):
                    timed_out = health_error is None and not cancelled.is_set()
                    try:
                        await self._request(
                            self.connection.cancel(session_id=self.session_id),
                            "session/cancel",
                            5,
                        )
                    except RunnerError:
                        if health_error is not None:
                            raise health_error from None
                        raise
                    self.cancel_sent = True
                    deadline = time.monotonic() + 5
                elif self.cancel_sent and time.monotonic() >= deadline:
                    if health_error is not None:
                        raise health_error
                    raise RunnerError(
                        "turn_timeout" if timed_out else "cancel_native_unconfirmed"
                    )
                await asyncio.wait({pending}, timeout=0.1)
            reply = await pending
            if health_error is not None:
                raise health_error
            if self.protocol_failed:
                raise RunnerError("runner_transport_failed")
            if timed_out:
                raise RunnerError("turn_timeout")
            return AcpTurn(
                session_id=self.session_id,
                stop_reason=reply.stop_reason,
                answer=self._answer(),
                updates=list(self.updates),
                usage=(
                    reply.usage.model_dump(
                        mode="json", by_alias=True, exclude_none=True
                    )
                    if getattr(reply, "usage", None) is not None
                    else None
                ),
            )
        except RunnerError:
            raise
        except (RequestError, ConnectionError, OSError, ValueError):
            if health_error is not None:
                raise health_error from None
            raise RunnerError("runner_transport_failed") from None
        finally:
            if not pending.done():
                pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)

    async def request_permission(self, session_id, tool_call, options, **kwargs):
        """Deny host permission requests regardless of agent labels or options."""
        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

    async def session_update(self, session_id, update, **kwargs):
        """Retain real updates and forward them to the owning activity capture."""
        if self.session_id is not None and session_id != self.session_id:
            self.protocol_failed = True
            return
        try:
            value = update.model_dump(mode="json", by_alias=True, exclude_none=True)
            self.updates.append(value)
            if self.on_update is not None:
                self.on_update(session_id, value)
        except Exception:
            self.protocol_failed = True

    async def ext_method(self, method, params):
        """Allow only pure output validation; every execution extension is denied."""
        if method == "laomedo/outputPrecheck" and self.on_precheck is not None:
            try:
                return self.on_precheck(params)
            except Exception:
                self.protocol_failed = True
                raise RequestError.internal_error() from None
        raise RequestError.method_not_found(method)

    async def ext_notification(self, method, params):
        """Forward provider telemetry only, without interpreting it as execution."""
        if self.on_extension is not None:
            try:
                self.on_extension(method, params)
            except Exception:
                self.protocol_failed = True

    def _answer(self) -> str:
        """Return the final message only, retaining commentary in the update log.

        Providers that identify messages are grouped by that native identity.
        For providers without message IDs, a non-message update separates runs
        of text chunks; earlier commentary must not enter a downstream payload.
        """
        messages = {}
        current = None
        anonymous = 0
        for update in self.updates:
            if update.get("sessionUpdate") != "agent_message_chunk":
                if update.get("sessionUpdate") in {"tool_call", "tool_call_update"}:
                    current = None
                continue
            if update.get("content", {}).get("type") != "text":
                continue
            identity = update.get("messageId")
            if identity is None:
                if current is None:
                    anonymous += 1
                    current = ("anonymous", anonymous)
                identity = current
            messages.setdefault(identity, []).append(update["content"]["text"])
        return "".join(next(reversed(messages.values()))) if messages else ""

    async def close(self) -> None:
        """Unblock the reader through creator-owned cleanup before closing SDK I/O."""
        try:
            self.session.close()
        finally:
            await self.connection.close()

    async def _request(self, request, method: str, seconds: float):
        """Map bounded SDK failures to existing safe runner error contracts."""
        try:
            result = await asyncio.wait_for(request, timeout=seconds)
            if self.protocol_failed:
                raise RunnerError("runner_transport_failed")
            return result
        except TimeoutError:
            raise RunnerError("request_timeout:" + method) from None
        except (RequestError, ConnectionError, OSError, ValueError):
            raise RunnerError("runner_transport_failed") from None
