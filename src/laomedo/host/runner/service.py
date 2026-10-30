"""Explicit startup of a host-configured local API; never dispatch model work."""

from __future__ import annotations

from pathlib import Path
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.request import ProxyHandler
from urllib.request import Request
from urllib.request import build_opener
import json
from laomedo._paths import import_root
from laomedo.host.runner.prerequisites import check_docker
from laomedo.host.runner.startup import startup_gate
from laomedo.host.runner.utils import service_environment
import socket
import subprocess
import sys
import threading
import time
import uuid


class RunnerService:
    def __init__(self, config_path):
        self.config_path = Path(config_path) if config_path else None
        self.lock = threading.Lock()
        self.process = None
        self.ready_process = None
        self.startup_id = None
        self.startup_gate_path = None
        self.cancel_requested = False
        self.opener = build_opener(ProxyHandler({}))
        self.docker_lock = threading.Lock()
        self.docker_checked_at = None
        self.docker_reason = None

    def config(self, url=None):
        if self.config_path is None:
            return None
        value = json.loads(self.config_path.read_text(encoding="utf-8"))
        required = {"provider", "state", "skill_store", "source", "port"}
        if not isinstance(value, dict) or value.get("provider") not in {
            "codex",
            "claude",
        }:
            raise ValueError("invalid_runner_service_config")
        # Retire persisted preview-only ceilings when reading older host configs.
        value = dict(value)
        value.pop("max_model_turns", None)
        if not required <= set(value):
            raise ValueError("invalid_runner_service_config")
        if not isinstance(value["state"], str):
            raise ValueError("absolute_runner_service_paths_required")
        value.setdefault("lease_service", str(Path(value["state"]).parent / "lease"))
        required.add("lease_service")
        if value["provider"] == "claude":
            from laomedo.agents.agents.claude.settings import IMAGE

            value.pop("executable", None)  # Retired host-runtime configuration.
            value.setdefault("image", IMAGE)
            value.setdefault("profile_volume", "laomedo-claude-profile")
            required.update({"image", "profile_volume", "lease_service"})
        optional = {
            "artifact_sources",
            "github_authority_store",
            "mediator_state",
            "git_workspace",
            "mirror_host_claude_login",
        }
        if not required <= set(value) or set(value) - required - optional:
            raise ValueError("invalid_runner_service_config")
        sources = value.get("artifact_sources", {})
        if (
            not isinstance(sources, dict)
            or any(
                provider not in {"codex", "claude", "opencode"}
                or not isinstance(path, str)
                or not Path(path).is_absolute()
                for provider, path in sources.items()
            )
            or type(value.get("git_workspace", False)) is not bool
            or type(value.get("mirror_host_claude_login", False)) is not bool
            or value.get("mirror_host_claude_login", False)
            and value["provider"] != "claude"
        ):
            raise ValueError("invalid_runner_service_config")
        if ("github_authority_store" in value) != ("mediator_state" in value):
            raise ValueError("invalid_runner_service_config")
        for key in ("github_authority_store", "mediator_state"):
            if key in value and (
                not isinstance(value[key], str) or not Path(value[key]).is_absolute()
            ):
                raise ValueError("absolute_runner_service_paths_required")
        if type(value["port"]) is not int or not 1 <= value["port"] <= 65535:
            raise ValueError("invalid_runner_service_port")
        for key in ("state", "skill_store", "source", "lease_service"):
            if not isinstance(value[key], str) or not Path(value[key]).is_absolute():
                raise ValueError("absolute_runner_service_paths_required")
        if url is not None and url != f"http://127.0.0.1:{value['port']}":
            return None
        return value

    def status(self, url=None, *, refresh=False):
        config = self.config(url)
        if config is None:
            return {"state": "unmanaged", "can_start": False}
        url = f"http://127.0.0.1:{config['port']}"
        token_path = Path(config["state"]) / "api-token"
        if not token_path.exists():
            return self._probe_listener(config, refresh=refresh)
        token = token_path.read_text(encoding="utf-8").strip()
        if not token:
            raise ValueError("runner_service_auth_unavailable")
        try:
            with self.opener.open(
                Request(
                    url + "/v1/health", headers={"Authorization": "Bearer " + token}
                ),
                timeout=1,
            ) as response:
                health = json.load(response)
            if (
                health.get("provider") != config["provider"]
                or health.get("status") != "ready"
            ):
                return {
                    "state": "unavailable",
                    "can_start": False,
                    "reason": "runner_identity_unverified",
                }
            process = self.process
            if process is not None and process.poll() is None:
                self.ready_process = process
            return self._with_docker(
                {"state": "ready", "can_start": False}, refresh=refresh
            )
        except HTTPError:
            return {
                "state": "unavailable",
                "can_start": False,
                "reason": "runner_identity_unverified",
            }
        except (URLError, TimeoutError, OSError):
            return self._probe_listener(config, refresh=refresh)

    def _probe_listener(self, config, *, refresh=False):
        # A health timeout does not prove the process is offline. Never replace
        # a listener whose identity/response cannot be established.
        try:
            with socket.create_connection(("127.0.0.1", config["port"]), timeout=3):
                return {
                    "state": "unavailable",
                    "can_start": False,
                    "reason": "runner_identity_unverified",
                }
        except ConnectionRefusedError:
            return self._with_docker(self._offline_state(), refresh=refresh)
        except OSError:
            return {
                "state": "unavailable",
                "can_start": False,
                "reason": "runner_identity_unverified",
            }

    def _with_docker(self, state, *, refresh=False):
        if state["state"] not in {"ready", "offline"}:
            return state
        if (
            refresh
            or self.docker_checked_at is None
            or time.monotonic() - self.docker_checked_at >= 2
        ):
            # Do not queue overlapping checks behind a slow CLI and exceed the
            # request deadline. Unknown prerequisites never permit a new spawn.
            if not self.docker_lock.acquire(blocking=False):
                return {
                    "state": "prerequisite",
                    "can_start": False,
                    "reason": "runner_docker_check_unconfirmed",
                    "runner_state": state["state"],
                }
            try:
                self.docker_reason = check_docker(service_environment("codex"))
                self.docker_checked_at = time.monotonic()
            finally:
                self.docker_lock.release()
        if self.docker_reason is not None:
            value = {
                "state": "prerequisite",
                "can_start": False,
                "reason": self.docker_reason,
                "runner_state": state["state"],
            }
            if state.get("reason") == "runner_start_cancelled":
                value["startup_cancelled"] = True
            return value
        if state["state"] == "offline" and not state.get("reason"):
            return {**state, "reason": "runner_local_offline"}
        return state

    def _offline_state(self):
        process = self.process
        if process is not None and process.poll() is None:
            return {
                "state": "cancelling" if self.cancel_requested else "starting",
                "can_start": False,
                "startup_id": self.startup_id,
            }
        cancelled = (
            self.cancel_requested
            and self.startup_gate_path is not None
            and self.startup_gate_path.with_suffix(".cancelled").exists()
        )
        return {
            "state": "offline",
            "can_start": True,
            "reason": (
                "runner_start_cancelled"
                if cancelled
                else (
                    "runner_start_failed"
                    if process is not None and self.ready_process is not process
                    else None
                )
            ),
        }

    def start(self, url=None):
        with self.lock:
            # A stale successful poll cannot authorize starting without Docker.
            current = self.status(url, refresh=True)
            if current["state"] != "offline" or not current["can_start"]:
                return current
            config = self.config(url)
            module = (
                "laomedo.agents.agents.claude.cli"
                if config["provider"] == "claude"
                else "laomedo.agents.agents.codex.cli"
            )
            # Load this installation even when Python is embedded/isolated and
            # ignores PYTHONPATH. Both bootstrap and module choice are fixed;
            # neither comes from a browser request or model output.
            bootstrap = (
                "import runpy,sys; sys.path.insert(0,sys.argv.pop(1)); "
                "module=sys.argv.pop(1); sys.argv[0]=module; "
                'runpy.run_module(module,run_name="__main__")'
            )
            command = [
                sys.executable,
                "-c",
                bootstrap,
                str(import_root()),
                module,
                "--state",
                config["state"],
                "--skill-store",
                config["skill_store"],
                "--source" if config["provider"] == "claude" else "--source-workspace",
                config["source"],
                "--lease-service",
                config["lease_service"],
                "--port",
                str(config["port"]),
            ]
            if config["provider"] == "claude":
                command.extend(
                    [
                        "--image",
                        config["image"],
                        "--profile-volume",
                        config["profile_volume"],
                    ]
                )
            for provider, state in sorted(config.get("artifact_sources", {}).items()):
                command.extend(["--artifact-source", provider + "=" + state])
            if "github_authority_store" in config:
                command.extend(
                    [
                        "--github-authority-store",
                        config["github_authority_store"],
                        "--mediator-state",
                        config["mediator_state"],
                    ]
                )
            if config.get("git_workspace"):
                command.append("--git-workspace")
            # The trusted host supplies all paths.
            # Neither browser inputs nor model outputs become process arguments.
            env = service_environment(config["provider"])
            if (
                config.get("mirror_host_claude_login") is True
                and config["provider"] == "claude"
            ):
                env["LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN"] = "1"
            self.cancel_requested = False
            self.startup_id = str(uuid.uuid4())
            self.startup_gate_path = (
                Path(config["state"]) / "startup-control" / (self.startup_id + ".lock")
            )
            env["LAOMEDO_STARTUP_GATE"] = str(self.startup_gate_path)
            log_path = Path(config["state"]) / "service-startup.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open("ab") as log:
                self.process = subprocess.Popen(
                    command,
                    cwd=import_root(),
                    env=env,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            return {
                "state": "starting",
                "can_start": False,
                "startup_id": self.startup_id,
            }

    def cancel_start(self, startup_id):
        with self.lock:
            current = self.status()
            if (
                not startup_id
                or startup_id != self.startup_id
                or current["state"] != "starting"
                or self.process is None
                or self.ready_process is self.process
            ):
                return current
            if self.startup_gate_path is None:
                return current
            # The API takes this same OS lock before binding its listener. It
            # cannot publish a listener after cancellation wins this lock.
            with startup_gate(self.startup_gate_path) as listening:
                if listening.exists():
                    return self.status()
                # Cooperative: the child finishes its bounded initialization
                # and cleanup, then refuses to bind. Never orphan its children.
                listening.with_suffix(".cancel").touch()
                self.cancel_requested = True
                return self._offline_state()
