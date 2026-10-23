"""Local Claude Code proposal runner; native tools and MCP are disabled.

The host retains its existing subscription login. No credential material is
copied into the workspace or exposed to a model tool. Files change only through
the separate, policy-checked operation service, never through this transport.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from uuid import UUID, uuid4

from .local_runner import LocalRunner, RunnerError, _copy_tree, _hash_tree, _json
from .output_contract import evaluate
from .skill_store import inventory, tree_hash
from . import workspace_skills
from .runner_activity import line_count, receipt
from .agent_activity import now


CLI_VERSION = "2.1.301"


def activity_usage(result):
    """Normalize cumulative session modelUsage; never add resumed totals together.

    Claude inputTokens excludes cache reads/writes; the shared activity schema
    includes them in inputTokens. Missing categories remain unknown.
    """
    models = result.get("modelUsage")
    if not isinstance(models, dict) or not models:
        return None
    keys = ("inputTokens", "cacheReadInputTokens", "cacheCreationInputTokens", "outputTokens")
    if any(not isinstance(value, dict) or any(type(value.get(key)) is not int or
           value[key] < 0 for key in keys) for value in models.values()):
        return None
    totals = {key: sum(value[key] for value in models.values()) for key in keys}
    inputs = totals["inputTokens"] + totals["cacheReadInputTokens"] + totals["cacheCreationInputTokens"]
    normalized = {"inputTokens": inputs, "cachedInputTokens": totals["cacheReadInputTokens"],
            "cacheWriteInputTokens": totals["cacheCreationInputTokens"],
            "outputTokens": totals["outputTokens"], "totalTokens": inputs + totals["outputTokens"]}
    if all(type(value.get("thinkingTokens")) is int and 0 <= value["thinkingTokens"] <= value["outputTokens"]
           for value in models.values()):
        normalized["reasoningOutputTokens"] = sum(value["thinkingTokens"] for value in models.values())
    return normalized
SYSTEM = ("Use the pinned skill instructions and the user's task. Native tools, "
          "commands, MCP and external writes are unavailable. Propose requested "
          "changes in your answer; the host validates and applies them. Do not "
          "claim an operation has been applied. When an output contract is "
          "provided, return exactly one JSON object, without fences or trailing text.")


def cli_environment():
    """Only OS/profile discovery needed by the official login, never service secrets."""
    allowed = {"PATH", "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "SYSTEMROOT",
               "WINDIR", "SYSTEMDRIVE", "COMSPEC", "PATHEXT", "TEMP", "TMP", "LANG",
               "LC_ALL", "LC_CTYPE", "HOMEDRIVE", "HOMEPATH", "PROGRAMDATA", "USERNAME"}
    return {**{key: value for key, value in os.environ.items() if key.upper() in allowed},
            "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1"}


def command(executable, model, effort, thread, *, resume=False):
    UUID(thread)
    return [str(executable), "--print", "--output-format", "json", "--model", model,
            "--effort", effort, "--max-turns", "1", "--tools", "",
            "--safe-mode", "--disable-slash-commands", "--setting-sources", "",
            "--settings", '{"hooks":{},"enabledPlugins":{},"autoMemoryEnabled":false}',
            "--strict-mcp-config", "--mcp-config", '{"mcpServers":{}}',
            "--permission-mode", "dontAsk", "--permission-prompts", "none",
            "--system-prompt", SYSTEM,
            "--resume" if resume else "--session-id", thread]


def terminal_result(text, thread):
    """Require Claude's terminal receipt; never repair its proposed answer."""
    try:
        value = json.loads(text)
    except (ValueError, TypeError):
        raise RunnerError("claude_terminal_receipt_invalid") from None
    if (not isinstance(value, dict) or value.get("type") != "result" or
            value.get("session_id") != thread):
        raise RunnerError("claude_session_identity_mismatch")
    if value.get("is_error") or value.get("subtype") != "success":
        raise RunnerError("claude_native_turn_failed")
    if value.get("num_turns", 1) != 1 or (value.get("subagent_stats") or {}).get("spawned", 0):
        raise RunnerError("claude_native_turn_limit_mismatch")
    if not isinstance(value.get("result"), str) or not value["result"].strip():
        raise RunnerError("completed_without_agent_message")
    return value


class ClaudeRunner(LocalRunner):
    provider = "claude"

    def __init__(self, state, skill_store, source_workspace, *, executable,
                 max_model_turns=0):
        self.executable = Path(executable).resolve(strict=True)
        version = subprocess.run([str(self.executable), "--version"], capture_output=True,
                                 text=True, timeout=20, check=True, env=cli_environment()).stdout.strip()
        if version != CLI_VERSION + " (Claude Code)":
            raise RunnerError("unsupported_claude_cli_version")
        # Provider overrides could silently select API billing or another account.
        if any(os.environ.get(key) for key in (
                "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
                "ANTHROPIC_BASE_URL", "CLAUDE_CONFIG_DIR", "CLAUDE_CODE_USE_BEDROCK",
                "CLAUDE_CODE_USE_VERTEX", "CLAUDE_CODE_USE_FOUNDRY")):
            raise RunnerError("claude_subscription_override_refused")
        self._check_auth()
        self.processes = {}
        super().__init__(state, skill_store, source_workspace, check_docker=False,
                         supervise_containers=False, max_model_turns=max_model_turns)

    def _check_auth(self):
        checked = subprocess.run([str(self.executable), "auth", "status"],
                                 capture_output=True, text=True, timeout=20, env=cli_environment())
        try:
            auth = json.loads(checked.stdout)
        except ValueError:
            raise RunnerError("claude_subscription_unavailable") from None
        if checked.returncode or not auth.get("loggedIn") or auth.get("authMethod") != "claude.ai":
            raise RunnerError("claude_subscription_unavailable")
        identity = {key: auth[key] for key in ("email", "orgId") if auth.get(key)}
        return "sha256:" + hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest() if identity else None

    def preflight(self):
        self._check_auth()
        return {"provider": self.provider, "cli_version": CLI_VERSION,
                "status": "ready", "native_tools": [], "credential_copy": False}

    def _prepare(self, request, **kwargs):
        if (not isinstance(request, dict) or not isinstance(request.get("model"), str) or
                not re.fullmatch(r"(?:sonnet|opus|haiku|claude-[A-Za-z0-9_.-]+)", request["model"])):
            raise RunnerError("claude_model_required")
        if request.get("effort") not in {"low", "medium", "high"}:
            raise RunnerError("unsupported_claude_effort")
        # This runner only proposes content; it does not expose a GitHub or shell scope.
        if request.get("github_authorization_ref") or request.get("handoff"):
            raise RunnerError("claude_proposal_scope_only")
        record = super()._prepare(request, **kwargs)
        record.update(provider=self.provider, runtime_version=CLI_VERSION,
                      execution_mode="host_proposal_only", profile=None, image=None,
                      image_id=None, cli_version="Claude Code " + CLI_VERSION,
                      config_sha256=None, native_tools=[])
        _json(self._run_dir(record["run_id"]) / "record.json", record)
        return record

    def _verify_skills(self, root, record):
        for skill in record["skills"]:
            path = root / "workspace/.agents/skills" / skill["skill_id"]
            if tree_hash(inventory(path)) != skill["tree_hash"]:
                raise RunnerError("pinned_skill_workspace_changed")
        workspace_skills.verify(root / "workspace", record["skills"], record["skill_git_exclusion"])
        if (_hash_tree(root / "canonical") != record["source_hash"] or
                (root / "store/sentinel.txt").read_text(encoding="utf-8") != "STORE-ORIGINAL"):
            raise RunnerError("protected_mount_changed")

    def _prompt(self, root, record, task):
        skills = []
        for skill in record["skills"]:
            files = []
            skipped = []
            for name in sorted(skill["file_hashes"]):
                content = (root / "workspace/.agents/skills" / skill["skill_id"] / name).read_bytes()
                try:
                    text = content.decode("utf-8")
                except UnicodeError:
                    skipped.append(name)
                    continue
                files.append({"path": name, "content": text})
            skills.append({"skill_id": skill["skill_id"], "revision_id": skill["revision_id"], "files": files})
            skill.update(delivery_mode="prompt_snapshot", use_evidence="included_in_prompt",
                         prompt_files=[item["path"] for item in files], skipped_binary_paths=skipped)
        prompt = json.dumps({"pinned_skills": skills, "task": task,
                             "output_requirements": record.get("output_requirements")}, ensure_ascii=False)
        if len(prompt.encode()) > 262144:
            raise RunnerError("claude_prompt_too_large")
        return prompt

    @staticmethod
    def _stop(process):
        if process.poll() is not None:
            return
        if os.name == "nt":
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        else:
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=15)

    def _invoke(self, root, record, prompt, flag, *, resume):
        args = command(self.executable, record["requested_model"], record["requested_effort"],
                       record["thread_id"], resume=resume)
        stdout_file, stderr_file = tempfile.TemporaryFile(), tempfile.TemporaryFile()
        try:
            process = subprocess.Popen(args, cwd=root / "workspace", stdin=subprocess.PIPE,
                                   stdout=stdout_file, stderr=stderr_file,
                                   encoding="utf-8", creationflags=(subprocess.CREATE_NO_WINDOW |
                                   subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0,
                                   start_new_session=os.name != "nt",
                                   env=cli_environment())
        except Exception:
            stdout_file.close()
            stderr_file.close()
            raise
        self.processes[record["run_id"]] = process
        deadline = time.monotonic() + 180
        try:
            first = True
            while True:
                if flag.is_set():
                    raise RunnerError("claude_cancelled")
                if time.monotonic() > deadline:
                    raise RunnerError("claude_turn_timeout")
                if os.fstat(stdout_file.fileno()).st_size > 4 * 1024 * 1024 or os.fstat(stderr_file.fileno()).st_size > 4 * 1024 * 1024:
                    raise RunnerError("claude_receipt_too_large")
                try:
                    process.communicate(prompt if first else None, timeout=.25)
                    break
                except subprocess.TimeoutExpired:
                    first = False
            stdout_file.seek(0)
            raw = stdout_file.read(4 * 1024 * 1024 + 1)
            if len(raw) > 4 * 1024 * 1024:
                raise RunnerError("claude_receipt_too_large")
            stdout = raw.decode("utf-8")
            # Store native stdout only; stderr can contain machine-specific details.
            with (root / "claude-results.jsonl").open("a", encoding="utf-8") as output:
                output.write(json.dumps({"stdout": stdout, "returncode": process.returncode}) + "\n")
            if process.returncode:
                raise RunnerError("claude_process_failed")
            return terminal_result(stdout, record["thread_id"])
        finally:
            prior_error = sys.exc_info()[0] is not None
            try:
                self._stop(process)
            except Exception:
                record["cleanup_error"] = "claude_parent_stop_unverified"
                if not prior_error:
                    raise RunnerError("claude_parent_stop_unverified") from None
            finally:
                record["parent_exit_observed"] = process.poll() is not None
                record["descendant_cleanup"] = "not_verified"
                self.processes.pop(record["run_id"], None)
                stdout_file.close()
                stderr_file.close()

    def _event(self, root, method, params):
        # These are explicitly adapter-normalized receipts, not Codex RPC events.
        event = {"method": method, "params": params, "provider": "claude",
                 "normalization": "claude-terminal-v1"}
        with (root / "activity-events.jsonl").open("a", encoding="utf-8") as output:
            output.write(json.dumps(receipt(event)) + "\n")

    def _execute(self, run_id, task, *, resume, activity_attempt_id=None):
        if not self.lock.acquire(blocking=False):
            raise RunnerError("runner_busy")
        record, attempt, flag = None, None, threading.Event()
        try:
            root, candidate = self._run_dir(run_id), self.status(run_id)
            if candidate["status"] != ("completed" if resume else "prepared"):
                raise RunnerError("run_not_dispatchable")
            record = candidate
            self.cancel_flags[run_id] = flag
            record.update(status="running", attempt_finished=False, snapshot_ready=False,
                          evidence_complete="unknown", completion_basis=None)
            self._verify_skills(root, record)
            identity = self._check_auth()
            if resume and (not identity or record.get("credential_subject_hash") != identity):
                raise RunnerError("resume_auth_identity_mismatch")
            record["credential_subject_hash"] = identity
            if not resume:
                record["thread_id"] = str(uuid4())
            attempt_id = activity_attempt_id if resume else record["activity_initial_attempt_id"]
            attempt_id = attempt_id or str(uuid4())
            UUID(attempt_id)
            folder = root / "activity-attempts"
            folder.mkdir(exist_ok=True)
            if (folder / (attempt_id + ".json")).exists():
                raise RunnerError("activity_attempt_already_exists")
            baseline = activity_usage({"modelUsage": record.get("native_model_usage")}) if resume else {}
            attempt = {"id": attempt_id, "native_start": line_count(root / "activity-events.jsonl"),
                       "otel_start": 0, "usage_baseline": {record["thread_id"]: {"total": baseline}}, "native_end": None,
                       "otel_end": None, "status": "running", "ended_at": None}
            _json(folder / (attempt_id + ".json"), attempt)
            record["activity_attempt_id"] = attempt_id
            self._event(root, "thread/started", {"thread": {"id": record["thread_id"]}})
            prompt = self._prompt(root, record, task)
            corrections = 0
            while True:
                if flag.is_set():
                    raise RunnerError("claude_cancelled")
                record["attempt_number"] = self._reserve_turn()
                _json(root / "record.json", record)
                host_turn = str(uuid4())
                self._event(root, "turn/started", {"threadId": record["thread_id"],
                                                   "turn": {"id": host_turn}, "identity_source": "host_attempt"})
                self._event(root, "item/completed", {"threadId": record["thread_id"], "turnId": host_turn,
                    "item": {"id": host_turn + ":prompt", "type": "userMessage",
                             "content": [{"type": "inputText", "text": prompt}],
                             "provenance": "host_submitted_prompt"}})
                try:
                    result = self._invoke(root, record, prompt, flag, resume=resume or corrections > 0)
                except Exception:
                    self._event(root, "thread/tokenUsage/updated", {"threadId": record["thread_id"],
                        "tokenUsage": {"total": None}, "usage_scope": "terminal_receipt_unavailable"})
                    self._event(root, "turn/completed", {"threadId": record["thread_id"],
                        "turn": {"id": host_turn, "status": "cancelled" if flag.is_set() else "failed"},
                        "identity_source": "host_attempt"})
                    raise
                totals = activity_usage(result)
                # Explicitly invalidate unknown resume baselines instead of charging
                # the entire session to the latest invocation.
                if resume and baseline is None:
                    totals = None
                elif resume and totals is not None and "reasoningOutputTokens" not in baseline:
                    totals.pop("reasoningOutputTokens", None)
                self._event(root, "thread/tokenUsage/updated", {"threadId": record["thread_id"],
                    "tokenUsage": {"total": totals}, "usage_scope": "native_session_cumulative"})
                self._event(root, "claude/result", {"threadId": record["thread_id"], "turnId": host_turn,
                    "subtype": result.get("subtype"), "duration_ms": result.get("duration_ms"),
                    "duration_api_ms": result.get("duration_api_ms"),
                    "native_session_id": result["session_id"], "tools_enabled": False,
                    "reported_models": list(result.get("modelUsage", {})) if isinstance(result.get("modelUsage"), dict) else [],
                    "evidence": "terminal_receipt_only", "usage_scope": "native_session_cumulative",
                    "reported_session_cost_usd": result.get("total_cost_usd"),
                    "cost_basis": "CLI estimate; cumulative session, not a subscription charge"})
                answer = result["result"]
                turn = {"turn_id": host_turn, "identity_source": "host_attempt", "status": "completed",
                        "input_hash": "sha256:" + hashlib.sha256(prompt.encode()).hexdigest(),
                        "native_session_id": result["session_id"]}
                record["turns"].append(turn)
                self._event(root, "item/completed", {"threadId": record["thread_id"], "turnId": host_turn,
                    "item": {"id": host_turn + ":answer", "type": "agentMessage", "text": answer}})
                self._event(root, "turn/completed", {"threadId": record["thread_id"],
                    "turn": {"id": host_turn, "status": "completed"}, "native_session_id": result["session_id"]})
                record.update(answer=answer, native_answer=answer, usage=result.get("usage"),
                              native_model_usage=result.get("modelUsage"),
                              output_correction_count=corrections,
                              precheck={"installed": False, "call_count": 0})
                models = result.get("modelUsage")
                record["effective_model"] = (next(iter(models)) if isinstance(models, dict) and len(models) == 1
                                             and all(isinstance(key, str) for key in models) else None)
                requirements = record.get("output_requirements")
                if not requirements:
                    break
                try:
                    submission = json.loads(answer)
                except ValueError as exc:
                    submission = None
                    parse_error = "trailing_data" if isinstance(exc, json.JSONDecodeError) and exc.msg == "Extra data" else "invalid_json"
                else:
                    parse_error = None
                validation = evaluate(requirements, submission)
                if parse_error:
                    validation.update(contract_status="rejected", errors=[{"path": "", "code": parse_error}])
                record["output_validation"] = validation
                turn["output_validation"] = validation
                if validation["contract_status"] == "accepted" or corrections >= record["output_retries"]:
                    break
                try:
                    self._turn_available()
                except RunnerError:
                    record["output_correction_blocked"] = "model_turn_cap_reached"
                    break
                prompt = json.dumps({"instruction": "Correct only the previous output. Return one JSON object, no fences or trailing characters. Do not repeat any action.",
                                     "validation": validation, "requirements": requirements})
                corrections += 1
            if flag.is_set():
                raise RunnerError("claude_cancelled")
            self._verify_skills(root, record)
            if _hash_tree(root / "canonical") != record["source_hash"]:
                raise RunnerError("protected_mount_changed")
            snapshot = root / "post-run-pending"
            digest = _copy_tree(root / "workspace", snapshot)
            if (root / "post-run").exists():
                workspace_skills.remove_owned_tree(root / "post-run", self.state)
            snapshot.rename(root / "post-run")
            record.update(status="completed", post_run_hash=digest, snapshot_ready=True,
                          output_ref=f"laomedo:run:{run_id}:workspace",
                          effective_effort=None,
                          evidence_complete="unknown", completion_basis="claude_terminal_receipt_only")
        except Exception as exc:
            if record is None:
                raise
            record.update(status="cancelled" if flag.is_set() else "failed",
                          error_category=str(exc) if isinstance(exc, RunnerError) else type(exc).__name__,
                          snapshot_ready=False, evidence_complete="unknown", completion_basis=None,
                          post_run_hash=None, output_ref=None)
        finally:
            if record is not None:
                record.update(attempt_finished=True, cancel_requested=flag.is_set())
                if attempt is not None:
                    attempt.update(native_end=line_count(self._run_dir(run_id) / "activity-events.jsonl"),
                                   otel_end=0, status=record["status"], ended_at=now())
                    _json(self._run_dir(run_id) / "activity-attempts" / (attempt["id"] + ".json"), attempt)
                _json(self._run_dir(run_id) / "record.json", record)
            self.cancel_flags.pop(run_id, None)
            self.lock.release()
        return record

    def resume(self, run_id, task, *, expected_post_run_hash, expected_thread_id, model, effort,
               activity_attempt_id=None):
        record = self.status(run_id)
        root = self._run_dir(run_id)
        if (record.get("provider") != self.provider or record.get("runtime_version") != CLI_VERSION or
                record.get("runner_instance_id") != self.instance_id or record["status"] != "completed" or
                record["thread_id"] != expected_thread_id or record["post_run_hash"] != expected_post_run_hash or
                record["requested_model"] != model or record["requested_effort"] != effort or
                not isinstance(task, str) or not task.strip()):
            raise RunnerError("resume_binding_mismatch")
        if _hash_tree(root / "workspace") != expected_post_run_hash:
            raise RunnerError("workspace_changed_since_snapshot")
        return self._execute(run_id, task, resume=True, activity_attempt_id=activity_attempt_id)

    def cancel(self, run_id):
        record = self.status(run_id)
        if record["status"] == "prepared":
            record.update(status="cancelled", cancel_requested=True, cancel_confirmed=True,
                          attempt_finished=True)
            _json(self._run_dir(run_id) / "record.json", record)
            return record
        if record["status"] == "running":
            flag = self.cancel_flags.get(run_id)
            if flag is None:
                raise RunnerError("run_not_active_in_this_process")
            flag.set()
            process = self.processes.get(run_id)
            if process:
                self._stop(process)
            return {**record, "cancel_requested": True, "cancel_confirmed": False}
        return record


def main():
    import argparse
    from .local_runner import serve
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--skill-store', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--max-model-turns', type=int, default=0)
    parser.add_argument('--port', type=int, default=8769)
    args = parser.parse_args()
    runner = ClaudeRunner(args.state, args.skill_store, args.source,
                          executable=args.executable, max_model_turns=args.max_model_turns)
    serve(runner, port=args.port).serve_forever()


if __name__ == '__main__':
    main()
