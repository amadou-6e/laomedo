"""Credential-free disposable check of a proposed Codex patch-deny hook."""

import json
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

import laomedo.local_runner as runner
from probe_mock_responses import MockResponses


def main():
    with tempfile.TemporaryDirectory(prefix="laomedo-hook-107-") as directory:
        root = Path(directory)
        for name in ("workspace", "canonical", "store", "evidence"):
            (root / name).mkdir()
        canary = "SYNTHETIC_PATCH_" + secrets.token_hex(12)
        script = root / "store" / "deny_patch.sh"
        script.write_text("#!/bin/sh\n"
            "printf '%s\\n' '{\"hookSpecificOutput\":{\"hookEventName\":"
            "\"PreToolUse\",\"permissionDecision\":\"deny\","
            "\"permissionDecisionReason\":\"Controller patch route blocked\"}}'\n")
        config = root / "config.toml"
        config.write_text(runner.CONFIG.read_text().replace(
            '"/home/runner/.codex/auth.json" = "deny"',
            '"/home/runner/.codex/auth.json" = "deny"\n'
            '"/home/runner/.codex" = "deny"') + "\n"
            "[[hooks.PreToolUse]]\nmatcher = '^apply_patch$'\n"
            "[[hooks.PreToolUse.hooks]]\ntype = 'command'\n"
            "command = 'sh /store/deny_patch.sh'\ntimeout = 5\n")
        profile = runner._split_profile(root.resolve())
        runner._ensure_split_profile(profile)
        original_config = runner.CONFIG
        runner.CONFIG = config
        server = None
        try:
            with MockResponses(tool_input=None) as mock:
                provider = (
                    'model_provider="laomedo_mock"',
                    'model_providers.laomedo_mock.name="Laomedo Mock"',
                    'model_providers.laomedo_mock.base_url="' + mock.base_url + '"',
                    'model_providers.laomedo_mock.env_key="ACCESS_TOKEN"',
                    'model_providers.laomedo_mock.wire_api="responses"',
                    'model_providers.laomedo_mock.requires_openai_auth=false',
                    'model_providers.laomedo_mock.supports_websockets=false',
                )
                server = runner.SplitAppServer(root / "workspace",
                    root / "canonical", root / "store", root / "evidence",
                    profile, provider_config=provider,
                    access_token="SYNTHETIC_ONLY")
                patch = ("*** Begin Patch\n*** Add File: "
                         "/home/runner/.codex/patch-sentinel.txt\n+" +
                         canary + "\n*** End Patch")
                mock.tool_input = (
                    "try { const result = await tools.apply_patch(" +
                    json.dumps(patch) + "); text('PATCH:' + "
                    "(result?.isError ? 'denied' : 'resolved')); } "
                    "catch { text('PATCH:denied'); }")
                initialized = server.request("initialize", {"clientInfo": {
                    "name": "laomedo_hook_probe", "title": "Hook Probe",
                    "version": "0.1.0"},
                    "capabilities": {"experimentalApi": True}}, timeout=30)
                if "result" not in initialized:
                    raise RuntimeError("initialize_rejected")
                server.notify("initialized", {})
                server.register_executor()
                thread = server.request("thread/start", {
                    "model": "gpt-6-luna", "cwd": "/draft",
                    "approvalPolicy": "never",
                    "environments": server.thread_environment()})
                thread_id = thread["result"]["thread"]["id"]
                turn = server.request("turn/start", {
                    "threadId": thread_id, "model": "gpt-6-luna",
                    "effort": "low", "cwd": "/draft",
                    "input": [{"type": "text", "text": "Synthetic hook probe"}],
                    "environments": server.turn_environment(),
                    "sandboxPolicy": {"type": "externalSandbox",
                                      "networkAccess": "restricted"}})
                status, error = server.wait_turn(turn["result"]["turn"]["id"],
                                                 50, threading.Event())
                archive = subprocess.run(["docker", "run", "--rm",
                    "--pull=never", "--network", "none", "--user", "10001:10001",
                    "--mount", f"type=volume,source={profile},target=/profile,readonly",
                    runner.IMAGE, "tar", "-cf", "-", "-C", "/", "profile"],
                    capture_output=True, timeout=15)
                if archive.returncode:
                    raise RuntimeError("profile_scan_failed")
                config_check = subprocess.run(["docker", "exec",
                    server.container_name, "grep", "-q", "hooks.PreToolUse",
                    "/home/runner/.codex/config.toml"], capture_output=True,
                    timeout=5)
                stderr_text = (root / "evidence" / "stderr.log").read_text(
                    errors="replace")
                result = {"schema_version": 1, "real_model_turns": 0,
                    "status": status, "error": error,
                    "config_contains_hook": config_check.returncode == 0,
                    "stderr_mentions_hook": "hook" in stderr_text.lower(),
                    "event_methods": sorted({str(event.get("method")) for event in
                                              server.events if "hook" in
                                              str(event.get("method", "")).lower()}),
                    "patch_reached_controller": canary.encode() in archive.stdout,
                    "hook_feedback_in_fake_request": any(
                        "PATCH:denied" in output
                        for request in mock.requests
                        for output in request["tool_outputs"]),
                    "fake_responses_requests": len(mock.requests)}
                print(json.dumps(result, sort_keys=True))
                if (result["status"] != "completed" or
                        not result["config_contains_hook"] or
                        not result["patch_reached_controller"] or
                        result["hook_feedback_in_fake_request"] or
                        result["fake_responses_requests"] != 2):
                    raise RuntimeError("patch_hook_negative_control_changed")
        finally:
            runner.CONFIG = original_config
            if server is not None:
                server.close()
            subprocess.run(["docker", "volume", "rm", profile],
                           capture_output=True, timeout=15)


if __name__ == "__main__":
    main()
