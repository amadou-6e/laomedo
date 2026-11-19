"""Dedicated app-owned composition around the existing provider and runner HTTP API."""

import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener

from laomedo.agents.registry import AgentProviderRegistry
from laomedo.host.http import NoRedirect
from laomedo.host.private_state.models import DirectoryPermissionPolicy
from laomedo.host.private_state.utils import prepare_private_directory
from laomedo.host.runner.http.server import RunnerServer
from laomedo.host.runner.service import RunnerService
from laomedo.integrations.langflow.assistant.errors import AssistantError


class AssistantRunner:
    """Own one profile's isolated runtime; no repository or publication authority is inherited."""

    def __init__(self, settings, owner, provider="codex"):
        """Retain trusted host composition, creating no model work or resources yet."""
        self.settings, self.owner, self.provider = settings, owner, provider
        self.agent = self.server = self.thread = None
        self.url = None
        self._token = None
        self.lock = threading.Lock()
        self.opener = build_opener(ProxyHandler({}), NoRedirect())

    def start(self):
        """Prepare an owned scratch source and compose only the selected configured provider."""
        with self.lock:
            if self.server is not None:
                return
            config = RunnerService(self.settings.runner_service_file).config()
            if not config or self.provider not in AgentProviderRegistry.provider_ids():
                raise AssistantError("assistant_setup_required", 503)
            options = {}
            if self.provider == "codex":
                if config["provider"] != "codex":
                    raise AssistantError("assistant_setup_required", 503)
                options["image_id"] = config.get("image_id")
            elif self.provider == "claude":
                profile = self.settings.claude_profile_volume
                if profile is None and config["provider"] == "claude":
                    profile = config["profile_volume"]
                if profile is None:
                    raise AssistantError("assistant_setup_required", 503)
                options["profile_volume"] = profile
            else:
                if self.settings.opencode_profile is None:
                    raise AssistantError("assistant_setup_required", 503)
                options["profile"] = self.settings.opencode_profile
            namespace = hashlib.sha256(self.settings.app_url.encode()).hexdigest()[:16]
            root = self.settings.state_root / namespace / str(self.owner)
            if self.provider != "codex":
                root = root / self.provider
            prepare_private_directory(
                root,
                policy=DirectoryPermissionPolicy.from_host(
                    deadline=time.monotonic() + 20
                ),
            )
            repository = root / "source-repository"
            repository.mkdir(exist_ok=True)
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
            source = repository / "workspace"
            source.mkdir(exist_ok=True)
            readme = source / "README.md"
            if not readme.exists():
                readme.write_text(
                    "# Laomedo assistant scratch workspace\nUse the scoped Laomedo MCP tools for workflow authoring. This is not the user's repository.\n",
                    encoding="utf-8",
                )
            agent = AgentProviderRegistry.create_agent(
                self.provider,
                root / "runner",
                Path(config["skill_store"]),
                source,
                lease_service=Path(config["lease_service"]),
                **options,
                artifact_sources={},
            )
            server = RunnerServer(agent, port=0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            try:
                thread.start()
            except BaseException:
                server.server_close()
                raise
            self.agent, self.server, self.thread = agent, server, thread
            self.url = "http://127.0.0.1:" + str(server.server_address[1])
            self._token = agent.api_token

    @property
    def instance_id(self):
        """Expose the composed Agent's host identity, never its transport credential."""
        return self.agent.instance_id if self.agent else None

    def request(self, method, path, body=None):
        """Issue one bounded authenticated local request without proxy, redirect or replay."""
        self.start()
        if not path.startswith("/v1/") or ".." in path or "\r" in path or "\n" in path:
            raise AssistantError("assistant_request_invalid", 400)
        request = Request(
            self.url + path,
            data=json.dumps(body).encode() if body is not None else None,
            method=method,
            headers={
                "Authorization": "Bearer " + self._token,
                "Content-Type": "application/json",
            },
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                data = response.read(4194305)
            if len(data) > 4194304:
                raise AssistantError("assistant_runner_response_too_large", 503)
            return json.loads(data)
        except HTTPError as error:
            try:
                payload = json.loads(error.read(65536))
                code = payload.get("error_category") or payload.get("code")
                if (
                    not isinstance(code, str)
                    or not code.replace("_", "").isalnum()
                    or len(code) > 100
                ):
                    code = "assistant_runner_unavailable"
            except (ValueError, TypeError):
                code = "assistant_runner_unavailable"
            finally:
                error.close()
            raise AssistantError(code, 409 if error.code < 500 else 503) from None
        except (URLError, TimeoutError, OSError, ValueError):
            raise AssistantError("assistant_dispatch_unknown", 503) from None

    def shutdown(self):
        """Stop only this owned HTTP listener; unfinished native work retains its recovery identity."""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.thread.join(5)

    def is_settled(self, run_id):
        """Observe common Agent ownership after native completion, not provider-private methods."""
        return (
            self.agent is not None
            and not self.agent.lock.locked()
            and self.agent.mcp_access(run_id) is None
        )
