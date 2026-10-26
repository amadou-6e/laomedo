"""Isolated Claude Code runner with persistent sessions and streamed native events."""

from __future__ import annotations

import hashlib
from concurrent.futures import Future, TimeoutError as FutureTimeout
from copy import deepcopy
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import queue
import threading
import time
from uuid import UUID, uuid4

from .local_runner import LocalRunner, RunnerError, _copy_tree, _hash_tree, _json
from .output_contract import evaluate
from .claude_login import mirror_login, LocalClaudeLoginError
from .skill_store import inventory, tree_hash
from . import workspace_skills
from .runner_activity import line_count, receipt
from .agent_activity import now
from .claude_models import EFFORTS


from .claude_container import ClaudeContainer, CommandService, IMAGE, PROFILE, CLI_VERSION, docker_environment
from .container_lease import cleanup_exact



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
SYSTEM = ("Work in /draft using the provided tools and pinned native skills. "
          "Read and edit files through the workspace command tool. Native controller "
          "file and shell tools are disabled. Only draft files may be changed. Commands execute in a separate "
          "credential-free container without network access. External GitHub effects "
          "require the scoped mediation tool or a validated downstream operation. "
          "Do not claim external changes without a successful receipt. When an output "
          "contract is provided, return exactly one JSON object without fences.")


def cli_environment():
    # This environment belongs to the Docker client, not to Claude. No host
    # profile or provider overrides are forwarded into containers.
    return docker_environment()


def command(executable, model, effort, thread, *, resume=False, output_only=False, skill_ids=()):
    UUID(thread)
    # The networked controller owns the subscription profile. Never expose its
    # filesystem through model-callable native tools. All file/command work
    # uses the credential-free worker, regardless of CLI path-policy behavior.
    tools = 'Skill' if skill_ids and not output_only else ''
    allowed = 'mcp__laomedo__exec_command,mcp__laomedo__github_operation'
    allowed += ''.join(',Skill(laomedo-pinned:' + name + ')' for name in skill_ids)
    return ['claude', '--print', '--output-format', 'stream-json', '--verbose',
            '--include-partial-messages', '--model', model,
            *(['--effort', effort] if effort != 'default' else []),
            '--restricted', '--tools', tools, '--setting-sources', '',
            '--settings', '{"disableAllHooks":true,"enabledPlugins":{},"autoMemoryEnabled":false}',
            '--strict-mcp-config', '--mcp-config', json.dumps({'mcpServers': {} if output_only else {
                'laomedo': {'command': 'python3', 'args': ['/opt/laomedo/command_mcp.py']}}}),
            '--allowedTools', allowed,
            '--disallowedTools', 'Read,Glob,Grep,Edit,Write,Bash,Agent,Task,WebFetch,WebSearch,NotebookEdit',
            '--permission-mode', 'dontAsk', '--permission-prompts', 'none',
            *([] if output_only else ['--plugin-dir', '/run/laomedo/pinned-skills']),
            '--append-system-prompt', SYSTEM,
            '--resume' if resume else '--session-id', thread]


def configuration_hash(model, effort, skills):
    frozen = command(None, model, effort, '00000000-0000-0000-0000-000000000000',
                     skill_ids=tuple(item['skill_id'] for item in skills))
    return 'sha256:' + hashlib.sha256(json.dumps(frozen, separators=(',', ':')).encode()).hexdigest()


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
    if (type(value.get("num_turns", 1)) is not int or value.get("num_turns", 1) < 1 or
            (value.get("subagent_stats") or {}).get("spawned", 0)):
        raise RunnerError("claude_native_turn_limit_mismatch")
    if not isinstance(value.get("result"), str) or not value["result"].strip():
        raise RunnerError("completed_without_agent_message")
    return value


def normalize_models(items):
    """Keep native picker IDs/labels and each model's advertised effort levels."""
    if not isinstance(items, list) or not items or len(items) > 256:
        raise ValueError('invalid_native_models')
    models, seen = [], set()
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('invalid_native_model')
        model, name, resolved = item.get('value'), item.get('displayName'), item.get('resolvedModel')
        if (not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.\[\]-]{0,159}', model)
                or model in seen or not isinstance(name, str) or not name.strip() or len(name) > 200
                or not isinstance(resolved, str) or not re.fullmatch(r'claude-[A-Za-z0-9_.-]{1,160}', resolved)):
            raise ValueError('invalid_native_model')
        seen.add(model)
        levels = item.get('supportedEffortLevels', [])
        if item.get('supportsEffort') is True:
            if (not isinstance(levels, list) or not levels
                    or any(not isinstance(level, str) or level not in EFFORTS or level == 'default' for level in levels)
                    or len(set(levels)) != len(levels)):
                raise ValueError('invalid_native_efforts')
        elif item.get('supportsEffort') not in (None, False) or levels:
            raise ValueError('invalid_native_efforts')
        else:
            levels = ['default']  # Explicitly omit --effort for models without this control.
        models.append({'id': model, 'name': name, 'resolved_model': resolved, 'efforts': levels})
    return models


class ClaudeRunner(LocalRunner):
    provider = "claude"

    def model_catalog(self, *, refresh=False):
        """Share an in-flight discovery across simultaneous editor refreshes."""
        with self._catalog_lock:
            cached = getattr(self, '_catalog_cached', None)
            if not refresh and cached and time.monotonic() - cached[0] < 300:
                return deepcopy(cached[1])
            pending = getattr(self, '_catalog_pending', None)
            owner = pending is None
            if owner:
                pending = self._catalog_pending = Future()
        if not owner:
            try:
                return deepcopy(pending.result(timeout=65))
            except FutureTimeout:
                raise RunnerError('runner_model_catalog_unavailable_check_runner_connection') from None
        try:
            result = self._discover_models()
            with self._catalog_lock:
                self._catalog_cached = (time.monotonic(), deepcopy(result))
            pending.set_result(result)
            return deepcopy(result)
        except Exception as exc:
            pending.set_exception(exc)
            raise
        finally:
            with self._catalog_lock:
                self._catalog_pending = None

    def _discover_models(self):
        """The native account picker, using only an initialize control request.

        No user message, session resume, model turn, or transcript is created.
        Bound the entire CLI lifetime below the component's HTTP deadline.
        """
        failure = 'runner_model_catalog_unavailable_check_runner_connection'
        self._check_auth(timeout=15)
        try:
            args = ['--print', '--input-format', 'stream-json', '--output-format', 'stream-json',
                    '--verbose', '--no-session-persistence', '--tools', '', '--restricted',
                    '--setting-sources', '', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                    '--permission-mode', 'dontAsk', '--permission-prompts', 'none']
            request_id = str(uuid4())
            payload = {'type': 'control_request', 'request_id': request_id,
                       'request': {'subtype': 'initialize', 'hooks': {}}}
            result = self.container.control(args, input=(json.dumps(payload)+'\n').encode(), timeout=45)
            raw = result.stdout
            if result.returncode or len(raw) > 1024 * 1024:
                raise ValueError('invalid_catalog_transport')
            responses = []
            for line in raw.decode('utf-8').splitlines():
                event = json.loads(line)
                if not isinstance(event, dict) or event.get('type') != 'control_response':
                    raise ValueError('unexpected_catalog_event')
                response = event['response']
                if (not isinstance(response, dict) or response.get('request_id') != request_id
                        or response.get('subtype') != 'success'):
                    raise ValueError('catalog_identity_mismatch')
                responses.append(response['response'])
            if len(responses) != 1:
                raise ValueError('catalog_response_missing')
            if not isinstance(responses[0], dict):
                raise ValueError('invalid_catalog_response')
            models = normalize_models(responses[0]['models'])
            return {'models': models, 'provider': 'claude', 'source': 'claude_cli_initialize',
                    'account_availability': 'cli_reported', 'submitted_turns': 0}
        except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError):
            raise RunnerError(failure) from None

    def __init__(self, state, skill_store, source_workspace, *, image=IMAGE,
                 profile_volume=PROFILE, lease_service=None, turn_timeout=180, container=None,
                 github_authority=None, mediator_state=None, git_workspace=False, artifact_sources=None):
        if type(turn_timeout) is not int or not 1 <= turn_timeout <= 86400:
            raise RunnerError('claude_turn_timeout_invalid')
        self.turn_timeout = turn_timeout
        self.container = container or ClaudeContainer(image, profile_volume, lease_service)
        self.executable = 'claude'
        self._catalog_lock = threading.Lock()
        self.processes = {}
        super().__init__(state, skill_store, source_workspace, check_docker=False,
                         supervise_containers=False, lease_service=lease_service, github_authority=github_authority,
                         mediator_state=mediator_state, git_workspace=git_workspace, artifact_sources=artifact_sources)
        self.profile = self.container.profile
        self.image, self.image_id = image, self.container.image_id

    def _check_auth(self, *, timeout=20):
        if os.environ.get('LAOMEDO_CLAUDE_MIRROR_HOST_LOGIN') == '1':
            try:
                mirror_login(self.container.profile, self.container.image_id)
            except LocalClaudeLoginError as error:
                if str(error) == 'claude_host_login_unavailable':
                    raise RunnerError('claude_host_login_unavailable') from None
                if str(error) == 'claude_host_login_expired':
                    raise RunnerError('claude_host_login_expired') from None
                raise RunnerError('claude_local_login_copy_failed') from None
        checked = self.container.control(['auth', 'status'], timeout=timeout)
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
                "status": "ready", "native_tools": ["Skill", "mcp__laomedo__exec_command"],
                "profile": self.profile, "image_id": self.image_id, "profile_mode": "dedicated_volume"}

    def _prepare(self, request, **kwargs):
        if (not isinstance(request, dict) or not isinstance(request.get("model"), str) or
                not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.\[\]-]{0,159}", request["model"])):
            raise RunnerError("claude_model_required")
        if request.get("effort") not in EFFORTS:
            raise RunnerError("unsupported_claude_effort")
        timeout = request.get('run_timeout_seconds', self.turn_timeout)
        if type(timeout) is not int or not 1 <= timeout <= 86400:
            raise RunnerError('claude_turn_timeout_invalid')
        # Explicit editor refresh owns discovery latency. Reuse the last native
        # selection for dispatch even after its editor-cache TTL; never silently
        # remap an alias during a slow concurrent refresh. A cold API client
        # still discovers once before any inference is accepted.
        with self._catalog_lock:
            cached = getattr(self, '_catalog_cached', None)
            selected_catalog = deepcopy(cached[1]) if cached else None
        choices = (selected_catalog or self.model_catalog())['models']
        choice = next((item for item in choices if item['id'] == request['model']), None)
        if choice is None:
            choice = next((item for item in choices if item['resolved_model'] == request['model']), None)
        if choice is None:
            raise RunnerError('claude_model_required')
        if request['effort'] not in choice['efforts']:
            raise RunnerError('unsupported_claude_effort')
        # Pinned native skills may instruct draft commands through the isolated
        # worker, but may not execute shell substitutions/hooks in the credential
        # controller or widen its frozen tools/model/session grant.
        references = request.get('skill_refs', [request['skill_ref']] if 'skill_ref' in request else [])
        if isinstance(references, list) and len(references) <= 16:
            for ref in references:
                if (not isinstance(ref, dict) or not isinstance(ref.get('skill_id'), str) or
                        not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', ref['skill_id']) or
                        not isinstance(ref.get('revision_id'), str) or
                        not re.fullmatch(r'sha256:[0-9a-f]{64}', ref['revision_id'])):
                    continue  # The shared validator supplies the stable input error.
                bundle = self.store.revision(ref['skill_id'], ref['revision_id'])
                for path in bundle['file_hashes']:
                    if Path(path).name != 'SKILL.md':
                        continue
                    try:
                        text = self.store.read_file(ref['skill_id'], ref['revision_id'], path)['content'].decode('utf-8-sig').replace('\r\n', '\n').replace('\r', '\n')
                    except UnicodeError:
                        raise RunnerError('skill_frontmatter_name_required') from None
                    if re.search(r'!`', text):
                        raise RunnerError('claude_native_skill_policy_unsupported')
                    # Reject ambiguous delimiters rather than guessing how the
                    # native loader interprets whitespace or unterminated YAML.
                    if not text.startswith('---\n') or '\n---\n' not in text[4:]:
                        raise RunnerError('claude_native_skill_policy_unsupported')
                    front = text[4:].split('\n---\n', 1)[0]
                    allowed = {'name', 'description', 'license', 'compatibility', 'metadata',
                               'argument-hint', 'user-invocable', 'disable-model-invocation'}
                    for line in front.splitlines():
                        if not line.strip() or line.lstrip().startswith('#') or line[0].isspace():
                            continue
                        key = re.match(r"^['\"]?([A-Za-z0-9_-]+)['\"]?\s*:", line)
                        if key is None or key.group(1) not in allowed:
                            raise RunnerError('claude_native_skill_policy_unsupported')
        record = super()._prepare(request, **kwargs)
        record.update(provider=self.provider, runtime_version=CLI_VERSION,
                      execution_mode="claude_container", profile=self.profile, image=self.image,
                      image_id=self.image_id, cli_version="Claude Code " + CLI_VERSION,
                      config_sha256=configuration_hash(choice['resolved_model'], request['effort'], record['skills']),
                      native_tools=(["Skill"] if record['skills'] else []) + ["mcp__laomedo__exec_command"],
                      turn_timeout=timeout, resolved_model=choice["resolved_model"],
                      permission_grant={"workspace": "draft-write", "commands": "network-free-worker",
                                        "profile": "controller-only", "external_effects": "host-mediated"})
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
        # Skills are native CLI plugin bundles, never text-truncated snapshots.
        for skill in record['skills']:
            skill.update(delivery_mode='native_plugin', use_evidence='offered')
        record['skill'] = deepcopy(record['skills'][0]) if len(record['skills']) == 1 else None
        return json.dumps({'task': task, 'workspace': '/draft',
                           'skills': [{'skill_id': x['skill_id'], 'revision_id': x['revision_id']}
                                      for x in record['skills']],
                           'imported_artifacts': record.get('imported_artifacts', []),
                           'output_requirements': record.get('output_requirements')}, ensure_ascii=False)

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
        name, token = 'laomedo-claude-' + uuid4().hex, uuid4().hex
        record['container_ownership'] = {'name': name, 'launch_token': token,
            'supervised': True, 'cleanup_verified': False}
        _json(root / 'record.json', record)
        lease = self.container.lease(record['run_id'], name, token, flag, record.get('github_scope'))
        deadline = record.get('_attempt_deadline', time.monotonic() + record['turn_timeout'])
        service, process = None, None
        output_only = record.get('output_correction_count', 0) > 0
        try:
            plugin = root / 'native-skill-plugin'
            (plugin / '.claude-plugin').mkdir(parents=True, exist_ok=True)
            _json(plugin / '.claude-plugin/plugin.json', {'name': 'laomedo-pinned', 'version': '1.0.0'})
            (plugin / 'skills').mkdir(exist_ok=True)
            (root / 'workspace/.claude/skills').mkdir(parents=True, exist_ok=True)
            mediation = None
            if record.get('github_scope'):
                if lease.grant_id is None:
                    raise RunnerError('mediated_grant_unavailable')
                route, instance = self._mediator_route()
                mediation = (route, instance, lease.dir / 'grant.secret')
            service = CommandService(self.container, root, record, flag, deadline, mediation=mediation)
            args = self.container.prefix(name=name, run_id=record['run_id'], token=token,
                                         workspace=root / 'workspace')
            args += ['--add-host', 'host.docker.internal:host-gateway',
                     '--mount', f'type=bind,source={plugin},target=/run/laomedo/pinned-skills,readonly',
                     '--mount', f'type=bind,source={root / "workspace/.agents/skills"},target=/run/laomedo/pinned-skills/skills,readonly',
                     '--mount', f'type=bind,source={service.secret_path},target=/run/laomedo/command-token,readonly',
                     '--env', 'LAOMEDO_COMMAND_URL=' + service.url,
                     '--env', 'LAOMEDO_GITHUB_GRANTED=' + ('1' if mediation else '0'),
                     '-i', self.image_id]
            args += command(None, record.get('resolved_model', record['requested_model']), record['requested_effort'],
                            record['thread_id'], resume=resume, output_only=output_only,
                            skill_ids=tuple(x['skill_id'] for x in record['skills']))[1:]
            messages = queue.Queue(maxsize=64)
            with tempfile.TemporaryFile() as errors:
                process = subprocess.Popen(['docker', *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=errors, env=docker_environment(), creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                self.processes[record['run_id']] = process
                def reader():
                    try:
                        while True:
                            line = process.stdout.readline(1024 * 1024 + 1)
                            if not line:
                                break
                            messages.put(line)
                    finally:
                        messages.put(None)
                threading.Thread(target=reader, daemon=True).start()
                with self.control_lock:
                    if flag.is_set():
                        raise RunnerError('claude_cancelled')
                    if time.monotonic() >= deadline:
                        raise RunnerError('claude_turn_timeout')
                    process.stdin.write(prompt.encode())
                    process.stdin.close()
                total, result = 0, None
                while True:
                    if flag.is_set():
                        raise RunnerError('claude_cancelled')
                    if time.monotonic() >= deadline:
                        raise RunnerError('claude_turn_timeout')
                    if os.fstat(errors.fileno()).st_size > 4 * 1024 * 1024:
                        raise RunnerError('claude_receipt_too_large')
                    try:
                        line = messages.get(timeout=.1)
                    except queue.Empty:
                        continue
                    if line is None:
                        break
                    total += len(line)
                    if len(line) > 1024 * 1024 or total > 32 * 1024 * 1024:
                        raise RunnerError('claude_receipt_too_large')
                    try:
                        event = json.loads(line)
                    except ValueError:
                        raise RunnerError('claude_terminal_receipt_invalid') from None
                    self._native_event(root, record, event)
                    if event.get('type') == 'result':
                        if result is not None:
                            raise RunnerError('claude_terminal_receipt_invalid')
                        result = event
                process.wait(timeout=10)
                if process.returncode or result is None:
                    raise RunnerError('claude_native_turn_failed')
                return terminal_result(json.dumps(result), record['thread_id'])
        finally:
            service_error = False
            if service is not None:
                try:
                    service.close()
                except Exception:
                    service_error = True
            verified, detail = cleanup_exact(name, record['run_id'], token)
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=15)
            self.processes.pop(record['run_id'], None)
            try:
                lease.finish()
            except RuntimeError:
                verified = False
            verified = verified and not service_error
            record['container_ownership'].update(cleanup_verified=verified, cleanup_detail=detail)
            record['descendant_cleanup'] = 'verified' if verified else 'not_verified'
            _json(root / 'record.json', record)
            if not verified:
                raise RunnerError('container_termination_unverified')

    def _native_event(self, root, record, event):
        if not isinstance(event, dict) or event.get('session_id', record['thread_id']) != record['thread_id']:
            raise RunnerError('claude_session_identity_mismatch')
        with (root / 'raw-events.jsonl').open('a', encoding='utf-8') as log:
            log.write(json.dumps(receipt(event)) + '\n')
        turn = record.get('active_host_turn')
        common = {'threadId': record['thread_id'], 'turnId': turn}
        if event.get('type') == 'system' and event.get('subtype') == 'init':
            record['native_initialization'] = {key: event.get(key) for key in ('model', 'tools', 'skills', 'permissionMode')}
            record['effective_model'] = event.get('model')
            record['effective_effort'] = event.get('effort')
            record['configured_effort'] = record['requested_effort']
            record['effective_effort_source'] = 'native_initialize' if event.get('effort') else 'not_reported'
        content = (event.get('message') or {}).get('content', [])
        tools = record.setdefault('_native_tool_calls', {})
        for index, block in enumerate(content if isinstance(content, list) else []):
            if not isinstance(block, dict):
                raise RunnerError('claude_terminal_receipt_invalid')
            if block.get('type') == 'tool_use':
                item = {'id': block['id'], 'type': 'dynamicToolCall', 'tool': block.get('name'),
                        'arguments': block.get('input'), 'status': 'running'}
                tools[block['id']] = item
                self._event(root, 'item/started', {**common, 'item': item})
            elif block.get('type') == 'tool_result':
                identity = block.get('tool_use_id')
                item = tools.pop(identity, {'id': identity, 'type': 'dynamicToolCall'})
                item = {**item, 'status': 'failed' if block.get('is_error') else 'completed',
                        'output': block.get('content'), 'isError': block.get('is_error', False)}
                self._event(root, 'item/completed', {**common, 'item': item})
                if item.get('tool') == 'Skill' and not item['isError']:
                    selected = (item.get('arguments') or {}).get('skill', '')
                    for skill in record['skills']:
                        if selected in {skill['skill_id'], 'laomedo-pinned:' + skill['skill_id']}:
                            skill['use_evidence'] = 'native_skill_tool_completed'
                    record['skill'] = deepcopy(record['skills'][0]) if len(record['skills']) == 1 else None
            elif block.get('type') in {'text', 'thinking'}:
                text = block.get('text', block.get('thinking', ''))
                if block['type'] == 'text':
                    record['_last_streamed_text'] = text
                self._event(root, 'item/completed', {**common, 'item': {
                    'id': str((event.get('message') or {}).get('id', event.get('uuid', turn))) + ':' + str(index),
                    'type': 'reasoning' if block['type'] == 'thinking' else 'agentMessage', 'text': text}})
        partial = event.get('event') if event.get('type') == 'stream_event' else None
        if isinstance(partial, dict):
            kind = partial.get('type')
            if kind == 'message_start':
                record['_stream_message_id'] = (partial.get('message') or {}).get('id', str(uuid4()))
                record['_stream_blocks'] = {}
            blocks = record.setdefault('_stream_blocks', {})
            index = str(partial.get('index', 0))
            if kind == 'content_block_start':
                block = partial.get('content_block') or {}
                if block.get('type') in {'text', 'thinking'}:
                    blocks[index] = {'id': record.get('_stream_message_id', turn) + ':' + index,
                        'type': 'reasoning' if block['type'] == 'thinking' else 'agentMessage',
                        'text': block.get('text', block.get('thinking', ''))}
                    self._event(root, 'item/started', {**common, 'item': dict(blocks[index])})
            elif kind == 'content_block_delta' and index in blocks:
                delta = partial.get('delta') or {}
                blocks[index]['text'] += delta.get('text', delta.get('thinking', ''))
                self._event(root, 'item/updated', {**common, 'item': dict(blocks[index])})
            elif kind == 'content_block_stop' and index in blocks:
                self._event(root, 'item/completed', {**common, 'item': blocks.pop(index)})
            elif kind == 'message_stop':
                record['_stream_blocks'] = {}

    def _event(self, root, method, params):
        # These are explicitly adapter-normalized receipts, not Codex RPC events.
        event = {"method": method, "params": params, "provider": "claude",
                 "normalization": "claude-stream-v2"}
        with (root / "activity-events.jsonl").open("a", encoding="utf-8") as output:
            output.write(json.dumps(receipt(event)) + "\n")

    def _execute(self, run_id, task, *, resume, activity_attempt_id=None):
        if not self.lock.acquire(blocking=False):
            raise RunnerError("runner_busy")
        record, attempt, flag = None, None, threading.Event()
        try:
            root = self._run_dir(run_id)
            with self.control_lock:
                candidate = self.status(run_id)
                if candidate['status'] == 'cancelled' and candidate.get('cancel_confirmed'):
                    return candidate
                if candidate['status'] != ('completed' if resume else 'prepared'):
                    raise RunnerError('run_not_dispatchable')
                record = candidate
                self.cancel_flags[run_id] = flag
                record.update(status='running', attempt_finished=False, snapshot_ready=False,
                              evidence_complete='unknown', completion_basis=None)
                record['_attempt_deadline'] = time.monotonic() + record['turn_timeout']
                _json(root / 'record.json', record)
            self._verify_skills(root, record)
            remaining = record['_attempt_deadline'] - time.monotonic()
            if remaining <= 0:
                raise RunnerError('claude_turn_timeout')
            identity = self._check_auth(timeout=min(60, remaining))
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
                record.pop("_last_streamed_text", None)
                record["active_host_turn"] = host_turn
                record["output_correction_count"] = corrections
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
                    "native_session_id": result["session_id"], "tools_enabled": corrections == 0,
                    "reported_models": list(result.get("modelUsage", {})) if isinstance(result.get("modelUsage"), dict) else [],
                    "evidence": "native_stream_and_receipt", "usage_scope": "native_session_cumulative",
                    "reported_session_cost_usd": result.get("total_cost_usd"),
                    "cost_basis": "CLI estimate; cumulative session, not a subscription charge"})
                answer = result["result"]
                turn = {"turn_id": host_turn, "identity_source": "host_attempt", "status": "completed",
                        "input_hash": "sha256:" + hashlib.sha256(prompt.encode()).hexdigest(),
                        "native_session_id": result["session_id"]}
                record["turns"].append(turn)
                if record.get('_last_streamed_text') != answer:
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
                self._turn_available()
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
                          evidence_complete="unknown", completion_basis="claude_native_stream_and_receipt")
        except Exception as exc:
            if record is None:
                raise
            record.update(status="cancelled" if flag.is_set() else "failed",
                          error_category=("claude_mediation_outcome_unknown" if record.get("mediation_outcome") == "unknown"
                                          else str(exc) if isinstance(exc, RunnerError) else type(exc).__name__),
                          snapshot_ready=False, evidence_complete="unknown", completion_basis=None,
                          post_run_hash=None, output_ref=None)
        finally:
            if record is not None:
                record['cancel_confirmed'] = bool(flag.is_set() and
                    record.get('container_ownership', {}).get('cleanup_verified') is True and
                    record.get('descendant_cleanup') == 'verified' and
                    record.get('mediation_outcome') != 'unknown')
                record.pop("_attempt_deadline", None)
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
                record.get("image_id") != self.image_id or record.get("profile") != self.profile or
                record.get("config_sha256") != configuration_hash(record.get('resolved_model'), effort, record.get('skills', [])) or
                record.get("permission_grant") != {"workspace": "draft-write", "commands": "network-free-worker",
                                                   "profile": "controller-only", "external_effects": "host-mediated"} or
                record.get("execution_mode") != "claude_container" or record["status"] != "completed" or
                record["thread_id"] != expected_thread_id or record["post_run_hash"] != expected_post_run_hash or
                record["requested_model"] != model or record["requested_effort"] != effort or
                not isinstance(task, str) or not task.strip()):
            raise RunnerError("resume_binding_mismatch")
        if not (root / "post-run").is_dir() or _hash_tree(root / "post-run") != expected_post_run_hash:
            raise RunnerError("post_run_snapshot_mismatch")
        if _hash_tree(root / "workspace") != expected_post_run_hash:
            raise RunnerError("workspace_changed_since_snapshot")
        return self._execute(run_id, task, resume=True, activity_attempt_id=activity_attempt_id)

    def cancel(self, run_id):
        with self.control_lock:
            record = self.status(run_id)
            if record['status'] == 'prepared':
                record.update(status='cancelled', cancel_requested=True, cancel_confirmed=True,
                              attempt_finished=True)
                _json(self._run_dir(run_id) / 'record.json', record)
                return record
        if record["status"] == "running":
            flag = self.cancel_flags.get(run_id)
            if flag is None:
                raise RunnerError("run_not_active_in_this_process")
            with self.control_lock:
                flag.set()
            # The execution loop owns teardown of both controller and workers.
            # Concurrent removals here race its finally block and can report a
            # spurious failure even though exact cleanup subsequently succeeds.
            # Acknowledge the request only; terminal status confirms cleanup.
            return {**record, "cancel_requested": True, "cancel_confirmed": False}
        return record


def main():
    import argparse
    from .local_runner import serve
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--skill-store', type=Path, required=True)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--image', default=IMAGE)
    parser.add_argument('--profile-volume', default=PROFILE)
    parser.add_argument('--lease-service', type=Path, required=True)
    parser.add_argument('--turn-timeout', type=int, default=180)
    parser.add_argument('--port', type=int, default=8769)
    parser.add_argument('--github-authority-store', type=Path)
    parser.add_argument('--mediator-state', type=Path)
    parser.add_argument('--git-workspace', action='store_true')
    parser.add_argument('--artifact-source', action='append', default=[], metavar='PROVIDER=STATE')
    args = parser.parse_args()
    if (args.github_authority_store is None) != (args.mediator_state is None):
        parser.error('GitHub authority and mediator state must be configured together')
    from .mediation_authority import RunGrantAuthority
    authority = RunGrantAuthority(args.github_authority_store) if args.github_authority_store else None
    runner = ClaudeRunner(args.state, args.skill_store, args.source,
                          image=args.image, profile_volume=args.profile_volume,
                          lease_service=args.lease_service, turn_timeout=args.turn_timeout,
                          github_authority=authority, mediator_state=args.mediator_state, git_workspace=args.git_workspace,
                          artifact_sources=dict(item.split("=",1) for item in args.artifact_source))
    # Discovery is control-only and belongs to startup/editor refresh, before
    # accepting async inference submissions with a short ACK deadline.
    runner.model_catalog()
    serve(runner, port=args.port).serve_forever()


if __name__ == '__main__':
    main()
