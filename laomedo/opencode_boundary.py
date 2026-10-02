"""Separate OpenCode controller credentials from Docker command workers."""

from __future__ import annotations

import base64
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import threading
import time
from urllib import error, request
from uuid import uuid4

from .local_runner import IMAGE as WORKER_IMAGE, IMAGE_ID as WORKER_IMAGE_ID, RunnerError, _json, _private
from .opencode_runner import CLI_VERSION


MIN_TOKEN_REMAINING_MS = 210000  # 180-second request timeout plus startup margin.


def check_auth_fresh(profile):
    path = Path(profile) / "auth-validity.json"
    try:
        validity = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RunnerError("opencode_auth_validity_required") from exc
    if not isinstance(validity, dict):
        raise RunnerError("opencode_auth_validity_invalid")
    try:
        key = json.loads((Path(profile) / "auth.json").read_text(encoding="utf-8"))["opencode-go"]["key"]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise RunnerError("opencode_private_auth_required") from exc
    if (not isinstance(key, str) or
            validity.get("credential_sha256") != hashlib.sha256(key.encode()).hexdigest()):
        raise RunnerError("opencode_auth_validity_mismatch")
    mode = validity.get("credential_mode")
    if mode == "provider_key" and validity.get("expires_at_ms") is None:
        return
    expiry = validity.get("expires_at_ms")
    if mode != "console_token" or not isinstance(expiry, int) or isinstance(expiry, bool):
        raise RunnerError("opencode_auth_validity_invalid")
    if expiry <= int(time.time() * 1000) + MIN_TOKEN_REMAINING_MS:
        raise RunnerError("opencode_console_token_refresh_required")


def worker_command(name, workspace, canonical, store, command):
    return ["docker", "run", "--rm", "--name", name, "--pull=never", "--network", "none",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "128",
            "--memory", "1g", "--user", "10001:10001",
            "--mount", f"type=bind,source={workspace},target=/draft",
            "--mount", f"type=bind,source={canonical},target=/canonical,readonly",
            "--mount", f"type=bind,source={store},target=/store,readonly",
            "--workdir", "/draft", WORKER_IMAGE, "sh", "-c", command]


class CommandBroker:
    def __init__(self, workspace, canonical, store, evidence):
        self.workspace, self.canonical, self.store = workspace, canonical, store
        self.evidence = evidence
        self.token = secrets.token_hex(32)
        self.active = set()
        self.lock = threading.Lock()
        self.capacity = threading.BoundedSemaphore(1)
        broker = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                if self.path != "/mcp" or self.headers.get("Authorization") != "Bearer " + broker.token:
                    self.send_error(403)
                    return
                msg = None
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if not 0 < length <= 65536:
                        raise ValueError("invalid_body")
                    msg = json.loads(self.rfile.read(length))
                    if "id" not in msg:
                        self.send_response(202)
                        self.end_headers()
                        return
                    value = broker.rpc(msg.get("method"), msg.get("params", {}))
                    body = {"jsonrpc": "2.0", "id": msg["id"], "result": value}
                except Exception:
                    body = {"jsonrpc": "2.0", "id": msg.get("id") if isinstance(msg, dict) else None,
                            "error": {"code": -32602, "message": "broker_request_failed"}}
                data = json.dumps(body).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        # Docker bridge must reach this host listener. A random bearer capability
        # is mandatory, and only one run's immutable mounts are addressable.
        self.server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        try:
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
            self.thread.start()
        except Exception:
            self.server.server_close()
            raise

    def rpc(self, method, params):
        if method == "initialize":
            return {"protocolVersion": "2024-11-05", "capabilities": {"tools": {}},
                    "serverInfo": {"name": "laomedo-command-worker", "version": "1"}}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": [{"name": "exec", "description": "Run a shell command in the isolated /draft workspace Docker worker. Credentials are not mounted.",
                "inputSchema": {"type": "object", "properties": {"command": {"type": "string"}},
                                "required": ["command"], "additionalProperties": False}}]}
        if method != "tools/call" or params.get("name") != "exec":
            raise RunnerError("unknown_worker_tool")
        command = params.get("arguments", {}).get("command")
        if not isinstance(command, str) or not command.strip() or len(command) > 16000:
            raise RunnerError("invalid_worker_command")
        result = self.execute(command)
        return {"content": [{"type": "text", "text": json.dumps(result)}], "isError": result["exit_code"] != 0}

    def execute(self, command):
        if not self.capacity.acquire(blocking=False):
            return {"exit_code": 75, "stdout": "", "stderr": "worker_busy"}
        name = "laomedo-oc-worker-" + uuid4().hex
        try:
            with self.lock:
                self.active.add(name)
            try:
                proc = subprocess.run(worker_command(name, self.workspace, self.canonical, self.store, command),
                                      capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
                value = {"exit_code": proc.returncode, "stdout": proc.stdout[:32768], "stderr": proc.stderr[:32768]}
            except subprocess.TimeoutExpired:
                value = {"exit_code": 124, "stdout": "", "stderr": "worker_timeout"}
            finally:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
                with self.lock:
                    self.active.discard(name)
            with (self.evidence / "worker-events.jsonl").open("a", encoding="utf-8") as log:
                log.write(json.dumps({"command": command, **value}) + "\n")
            return value
        finally:
            self.capacity.release()

    def close(self):
        self.server.shutdown()
        with self.lock:
            names = list(self.active)
        for name in names:
            subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)
        # Stop owned command workers before joining request-handler threads.
        self.server.server_close()
        self.thread.join(timeout=5)


class IsolatedOpenCode:
    """One controller per turn, persistent session profile, independent workers."""

    def __init__(self, workspace, evidence, *, profile, image, image_id):
        self.profile = _private(Path(profile))
        if not (self.profile / "auth.json").is_file():
            raise RunnerError("opencode_private_auth_required")
        self.check_auth_fresh()
        identity_path = self.profile / "identity.json"
        if not identity_path.exists():
            _json(identity_path, {"profile_id": str(uuid4())})
        self.runtime_identity = {"provider": "opencode", "runtime_version": CLI_VERSION,
            "image": image, "image_id": image_id,
            "profile_id": json.loads(identity_path.read_text())["profile_id"]}
        for label, expected in ((image, image_id), (WORKER_IMAGE, WORKER_IMAGE_ID)):
            actual = subprocess.run(["docker", "image", "inspect", label, "--format", "{{.Id}}"],
                                    check=True, capture_output=True, text=True, timeout=15).stdout.strip()
            if actual != expected:
                raise RunnerError("opencode_image_pin_mismatch")
        root = evidence / ("controller-" + uuid4().hex)
        root.mkdir()
        view = root / "view"
        view.mkdir()
        # No user project configs/custom tools are ever mounted in the controller.
        shutil.copytree(workspace / ".agents", view / ".agents")
        self.broker = None
        self.log = None
        self.name = None
        try:
            self.broker = CommandBroker(workspace, evidence / "canonical", evidence / "store", evidence)
            self.password = secrets.token_hex(32)
            self.name = "laomedo-oc-controller-" + uuid4().hex
            self.log = (evidence / "raw-events.jsonl").open("a", encoding="utf-8")
            permissions = {"*": "deny", "laomedo_exec": "allow", "skill": {"*": "deny"}}
            for skill in (view / ".agents/skills").iterdir():
                permissions["skill"][skill.name] = "allow"
            config = {"$schema": "https://opencode.ai/config.json", "autoupdate": False, "share": "disabled",
                "plugin": [], "mcp": {"laomedo": {"type": "remote", "url":
                    f"http://host.docker.internal:{self.broker.server.server_port}/mcp",
                    "headers": {"Authorization": "Bearer " + self.broker.token}, "oauth": False}},
                "permission": permissions, "tools": {"*": False, "skill": True, "laomedo_exec": True}}
            provider_options = self.profile / "provider-options.json"
            if provider_options.exists():
                supplied = json.loads(provider_options.read_text(encoding="utf-8"))
                organization = supplied.get("provider", {}).get("opencode-go", {}).get("options", {}).get("headers", {}).get("x-opencode-org-id")
                if not isinstance(organization, str) or not organization:
                    raise RunnerError("opencode_organization_context_invalid")
                routing = supplied["provider"]["opencode-go"]
                if (routing.get("api") != "https://opencode.ai/inference/go/openai/v1" or
                        routing.get("npm") != "@ai-sdk/openai-compatible"):
                    raise RunnerError("opencode_console_provider_routing_not_allowed")
                config["provider"] = {"opencode-go": {"api": routing["api"], "npm": routing["npm"],
                    "models": routing.get("models", {}),
                    "options": {"headers": {"x-opencode-org-id": organization}}}}
            _json(root / "config.json", config)
            self.profile.joinpath("sessions").mkdir(exist_ok=True)
        except Exception:
            self.close()
            raise
        cmd = ["docker", "run", "-d", "--name", self.name, "--pull=never", "--network", "bridge",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges", "--pids-limit", "128", "--memory", "1g",
            "--user", "10001:10001", "-p", "127.0.0.1::4096",
            "--mount", f"type=bind,source={view},target=/draft,readonly",
            "--mount", f"type=bind,source={root / 'config.json'},target=/controller-config.json,readonly",
            "--mount", f"type=bind,source={self.profile / 'sessions'},target=/home/runner/.local/share/opencode",
            "--mount", f"type=bind,source={self.profile / 'auth.json'},target=/home/runner/.local/share/opencode/auth.json,readonly",
            "-e", "OPENCODE_CONFIG=/controller-config.json", "-e", "OPENCODE_DISABLE_PROJECT_CONFIG=true",
            "-e", "OPENCODE_SERVER_PASSWORD=" + self.password, "-e", "HOME=/home/runner",
            "-e", "XDG_STATE_HOME=/tmp/opencode-state", "-e", "XDG_CACHE_HOME=/tmp/opencode-cache",
            "-e", "XDG_CONFIG_HOME=/tmp/opencode-config",
            "--workdir", "/draft", image,
            "opencode", "serve", "--pure", "--hostname", "0.0.0.0", "--port", "4096"]
        try:
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
            self.port = subprocess.run(["docker", "port", self.name, "4096/tcp"], check=True,
                capture_output=True, text=True, timeout=15).stdout.strip().rsplit(":", 1)[1]
            for _ in range(40):
                try:
                    if self.call("GET", "/global/health").get("healthy"):
                        break
                except (OSError, error.URLError):
                    running = subprocess.run(["docker", "inspect", self.name, "--format", "{{.State.Running}}"],
                                             capture_output=True, text=True, timeout=10).stdout.strip()
                    if running != "true":
                        raise RunnerError("opencode_controller_startup_failed")
                    time.sleep(.25)
            else:
                raise RunnerError("opencode_controller_not_ready")
        except Exception:
            logs = subprocess.run(["docker", "logs", self.name], capture_output=True, timeout=15)
            (root / "startup.log").write_bytes(logs.stdout + logs.stderr)
            self.close()
            raise

    def call(self, method, path, payload=None):
        basic = base64.b64encode(("opencode:" + self.password).encode()).decode()
        req = request.Request("http://127.0.0.1:" + self.port + path + "?directory=/draft",
            data=None if payload is None else json.dumps(payload).encode(),
            headers={"Authorization": "Basic " + basic, "Content-Type": "application/json"}, method=method)
        with request.urlopen(req, timeout=3 if path == "/global/health" else 180) as response:
            raw = response.read()
            value = json.loads(raw) if raw else None
        # Raw provider records stay in private run evidence. Request credentials
        # and config responses are never placed in the provider trace.
        if path not in {"/config", "/provider"}:
            self.log.write(json.dumps({"method": method, "path": path, "response": value}) + "\n")
            self.log.flush()
        return value

    def close(self):
        try:
            if self.name is not None:
                subprocess.run(["docker", "rm", "-f", self.name], capture_output=True, timeout=15)
                self.name = None
        finally:
            try:
                if self.broker is not None:
                    self.broker.close()
                    self.broker = None
            finally:
                if self.log is not None:
                    self.log.close()
                    self.log = None

    def check_auth_fresh(self):
        check_auth_fresh(self.profile)
