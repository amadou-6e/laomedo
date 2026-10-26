"""Claude controller containers and credential-free, network-free command workers."""
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import math
import re
import secrets
import subprocess
import threading
import time
from uuid import uuid4

from .container_lease import LABEL_RUN, LABEL_TOKEN, cleanup_exact
from .lease_service import LeaseClient, SERVICE_STALE_SECONDS
from .local_runner import RunnerError, _json

IMAGE = 'laomedo-claude-controller:2.1.310'
PROFILE = 'laomedo-claude-profile'
CLI_VERSION = '2.1.310'


def docker_environment():
    """Docker configuration is host-owned; provider overrides never reach agents."""
    import os
    keys = {'PATH', 'SYSTEMROOT', 'WINDIR', 'HOME', 'USERPROFILE', 'APPDATA',
            'LOCALAPPDATA', 'TEMP', 'TMP', 'DOCKER_HOST', 'DOCKER_CONTEXT',
            'DOCKER_CONFIG', 'DOCKER_CERT_PATH', 'DOCKER_TLS_VERIFY'}
    return {k: v for k, v in os.environ.items() if k.upper() in keys}


def run_docker(args, **kwargs):
    try:
        return subprocess.run(['docker', *args], env=docker_environment(),
                              capture_output=True, **kwargs)
    except (OSError, subprocess.SubprocessError):
        raise RunnerError('claude_container_unavailable') from None


class ClaudeContainer:
    def __init__(self, image=IMAGE, profile=PROFILE, lease_service=None):
        if not isinstance(image, str) or not re.fullmatch(r'[A-Za-z0-9_./:@-]+', image):
            raise RunnerError('claude_container_configuration_invalid')
        if not isinstance(profile, str) or not re.fullmatch(r'laomedo-claude-[a-z0-9-]+', profile):
            raise RunnerError('claude_container_configuration_invalid')
        checked = run_docker(['image', 'inspect', image], text=True, timeout=20)
        try:
            self.image_id = json.loads(checked.stdout)[0]['Id']
            if checked.returncode or not re.fullmatch(r'sha256:[0-9a-f]{64}', self.image_id):
                raise ValueError()
        except (ValueError, KeyError, IndexError, TypeError):
            raise RunnerError('claude_container_image_missing') from None
        self.profile, self.lease_service = profile, lease_service
        self.check_supervisor()
        volume = run_docker(['volume', 'inspect', profile], text=True, timeout=15)
        if volume.returncode:
            created = run_docker(['volume', 'create', '--label', 'laomedo.provider=claude', profile],
                                 text=True, timeout=15)
            if created.returncode:
                raise RunnerError('claude_container_profile_unavailable')
            volume = run_docker(['volume', 'inspect', profile], text=True, timeout=15)
        try:
            if json.loads(volume.stdout)[0]['Labels'].get('laomedo.provider') != 'claude':
                raise ValueError()
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise RunnerError('claude_container_profile_unavailable') from None
        version = self.control(['--version'], timeout=60)
        if version.returncode or version.stdout.decode().strip() != CLI_VERSION + ' (Claude Code)':
            raise RunnerError('unsupported_claude_cli_version')

    def prefix(self, *, name=None, run_id=None, token=None, workspace=None, worker=False):
        args = ['run', '--rm', '--init', '--cap-drop=ALL', '--security-opt=no-new-privileges',
                '--read-only', '--pids-limit=128', '--memory=1g', '--cpus=2',
                '--tmpfs', '/tmp:rw,nosuid,nodev,size=256m', '--workdir', '/draft']
        if name:
            args += ['--name', name, '--label', LABEL_RUN + '=' + run_id,
                     '--label', LABEL_TOKEN + '=' + token]
        if worker:
            args += ['--network=none', '--env', 'HOME=/tmp', '--env', 'CLAUDE_CONFIG_DIR=/tmp/unused']
        else:
            args += ['--mount', f'type=volume,source={self.profile},target=/profile']
        if workspace:
            args += ['--mount', f'type=bind,source={workspace},target=/draft',
                     '--mount', f'type=bind,source={workspace / ".agents/skills"},target=/draft/.agents/skills,readonly',
                     '--mount', f'type=bind,source={workspace / ".agents/skills"},target=/draft/.claude/skills,readonly']
        return args

    def check_supervisor(self):
        """Never advertise a runnable API without independent cleanup supervision."""
        from pathlib import Path
        if self.lease_service is None:
            raise RunnerError('lease_service_required')
        try:
            root = Path(self.lease_service)
            info = json.loads((root / 'service.json').read_text())
            wall = float((root / 'service.alive').read_text())
            monotonic = float((root / 'service.alive.monotonic').read_text())
            if (not isinstance(info.get('pid'), int) or not info.get('instance') or
                    not math.isfinite(wall) or not math.isfinite(monotonic) or
                    not -1 <= time.time() - wall <= SERVICE_STALE_SECONDS or
                    not -1 <= time.monotonic() - monotonic <= SERVICE_STALE_SECONDS):
                raise ValueError()
        except (OSError, ValueError, TypeError, AttributeError):
            raise RunnerError('lease_service_unavailable') from None

    def control(self, args, *, input=None, timeout=45):
        # An in-container timeout also applies if the host process disappears.
        prefix = self.prefix() + ['--entrypoint', 'timeout', '-i', self.image_id,
                                  str(timeout), 'claude', *args]
        return run_docker(prefix, input=input, timeout=timeout + 10)

    def lease(self, run_id, name, token, cancelled, scope=None):
        if self.lease_service is None:
            raise RunnerError('lease_service_required')
        try:
            return LeaseClient(self.lease_service, run_id=run_id, name=name,
                               token=token, cancelled=cancelled, mediation_request=scope)
        except (OSError, RuntimeError):
            raise RunnerError('lease_service_unavailable') from None


class CommandService:
    """One run capability; all commands execute without the Claude profile/network."""
    def __init__(self, runtime, root, record, cancelled, deadline, *, mediation=None):
        self.runtime, self.root, self.record = runtime, root, record
        self.cancelled, self.deadline = cancelled, deadline
        self.mediation = mediation
        self.token = secrets.token_hex(32)
        self.lock = threading.Lock()
        self.cleanup_failed = False
        self.active_lock = threading.Lock()
        self.active = {}
        self.closed = False
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass

            def do_POST(self):
                if self.path != '/command' or not secrets.compare_digest(
                        self.headers.get('Authorization', ''), 'Bearer ' + owner.token):
                    self.send_error(403)
                    return
                try:
                    size = int(self.headers.get('Content-Length', '0'))
                    if not 0 < size <= 65536:
                        raise ValueError()
                    value = json.loads(self.rfile.read(size))
                    answer = owner.mediate(value['github']) if isinstance(value, dict) and set(value) == {'github'} else owner.execute(value)
                    raw = json.dumps(answer).encode()
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Content-Length', str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)
                except Exception:
                    self.send_error(503, 'Workspace command unavailable')

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.secret_path = root / ('command-capability-' + uuid4().hex)
        self.secret_path.write_text(self.token, encoding='ascii')
        self.url = f'http://host.docker.internal:{self.server.server_port}/command'

    def execute(self, value):
        if not isinstance(value, dict) or set(value) != {'command'} or not isinstance(value['command'], str):
            raise RunnerError('claude_workspace_command_invalid')
        if not value['command'].strip() or len(value['command']) > 60000:
            raise RunnerError('claude_workspace_command_invalid')
        with self.lock:
            if self.closed or self.cancelled.is_set() or time.monotonic() >= self.deadline:
                raise RunnerError('claude_cancelled')
            name, token = 'laomedo-claude-command-' + uuid4().hex, uuid4().hex
            lease = self.runtime.lease(self.record['run_id'], name, token, self.cancelled)
            prefix = self.runtime.prefix(name=name, run_id=self.record['run_id'], token=token,
                                         workspace=self.root / 'workspace', worker=True)
            with self.active_lock:
                self.active[name] = token
            try:
                result = run_docker(prefix + ['--entrypoint', 'sh', self.runtime.image_id,
                                    '-c', value['command']], timeout=min(120, max(1, self.deadline - time.monotonic())))
                return {'exit_code': result.returncode,
                        'output': (result.stdout + result.stderr)[:1024 * 1024].decode('utf-8', errors='replace')}
            finally:
                verified, _ = cleanup_exact(name, self.record['run_id'], token)
                try:
                    lease.finish()
                except RuntimeError:
                    verified = False
                with self.active_lock:
                    self.active.pop(name, None)
                if not verified:
                    self.cleanup_failed = True
                    self.cancelled.set()
                    raise RunnerError('container_termination_unverified')

    def mediate(self, value):
        from urllib.request import Request, urlopen
        from urllib.error import HTTPError
        if self.mediation is None or self.closed or self.cancelled.is_set():
            raise RunnerError('mediated_grant_unavailable')
        if (not isinstance(value, dict) or set(value) - {'operation', 'payload', 'effect_id'} or
                not isinstance(value.get('operation'), str) or not isinstance(value.get('payload'), dict)):
            raise RunnerError('claude_workspace_command_invalid')
        url, instance, secret_path = self.mediation
        body = {**value, 'repository': self.record['github_scope']['repository']}
        request = Request(url.replace('host.docker.internal', '127.0.0.1'),
            data=json.dumps(body).encode(), headers={'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + secret_path.read_text().strip(),
            'X-Laomedo-Mediator-Instance': instance})
        try:
            with urlopen(request, timeout=20) as response:
                return json.load(response)
        except HTTPError:
            # A known refusal is terminal for this request and contains no raw response.
            return {'error': 'mediation_request_refused'}
        except Exception:
            self.record['mediation_outcome'] = 'unknown'
            self.cancelled.set()
            raise RunnerError('claude_mediation_outcome_unknown') from None

    def close(self):
        self.closed = True
        with self.active_lock:
            active = list(self.active.items())
        for name, token in active:
            verified, _ = cleanup_exact(name, self.record['run_id'], token)
            if not verified:
                self.cleanup_failed = True
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        # Wait for any command's exact cleanup before freezing the workspace.
        with self.lock:
            self.secret_path.unlink(missing_ok=True)
        if self.cleanup_failed:
            raise RunnerError('container_termination_unverified')
