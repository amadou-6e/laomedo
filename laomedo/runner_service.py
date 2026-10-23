"""Explicit startup of a host-configured local API; never dispatch model work."""
import json
import os
from pathlib import Path
import subprocess
import socket
import sys
import threading
from urllib.error import URLError, HTTPError
from urllib.request import Request, build_opener, ProxyHandler


def service_environment(provider):
    allowed = {'PATH', 'HOME', 'USERPROFILE', 'APPDATA', 'LOCALAPPDATA', 'SYSTEMROOT',
        'WINDIR', 'SYSTEMDRIVE', 'COMSPEC', 'PATHEXT', 'TEMP', 'TMP', 'LANG',
        'LC_ALL', 'LC_CTYPE', 'HOMEDRIVE', 'HOMEPATH', 'PROGRAMDATA', 'USERNAME'}
    if provider == 'codex':
        allowed.update({'DOCKER_HOST', 'DOCKER_TLS_VERIFY', 'DOCKER_CERT_PATH',
                        'DOCKER_CONTEXT', 'DOCKER_CONFIG'})
    return {**{key: value for key, value in os.environ.items() if key.upper() in allowed},
            'PYTHONPATH': str(Path(__file__).resolve().parents[1])}


class RunnerService:
    def __init__(self, config_path):
        self.config_path = Path(config_path) if config_path else None
        self.lock = threading.Lock()
        self.process = None
        self.opener = build_opener(ProxyHandler({}))

    def config(self, url=None):
        if self.config_path is None:
            return None
        value = json.loads(self.config_path.read_text(encoding='utf-8'))
        required = {'provider', 'state', 'skill_store', 'source', 'port', 'max_model_turns'}
        if not isinstance(value, dict) or value.get('provider') not in {'codex', 'claude'}:
            raise ValueError('invalid_runner_service_config')
        if value['provider'] == 'claude':
            required.add('executable')
        if set(value) != required:
            raise ValueError('invalid_runner_service_config')
        if type(value['port']) is not int or not 1 <= value['port'] <= 65535:
            raise ValueError('invalid_runner_service_port')
        if type(value['max_model_turns']) is not int or value['max_model_turns'] < 0:
            raise ValueError('invalid_runner_service_budget')
        for key in ('state', 'skill_store', 'source') + (('executable',) if value['provider'] == 'claude' else ()):
            if not isinstance(value[key], str) or not Path(value[key]).is_absolute():
                raise ValueError('absolute_runner_service_paths_required')
        if url is not None and url != f"http://127.0.0.1:{value['port']}":
            return None
        return value

    def status(self, url=None):
        config = self.config(url)
        if config is None:
            return {'state': 'unmanaged', 'can_start': False}
        url = f"http://127.0.0.1:{config['port']}"
        token_path = Path(config['state']) / 'api-token'
        if not token_path.exists():
            try:
                with socket.create_connection(('127.0.0.1', config['port']), timeout=.25):
                    return {'state': 'unavailable', 'can_start': False, 'reason': 'runner_identity_unverified'}
            except OSError:
                return self._offline_state()
        token = token_path.read_text(encoding='utf-8').strip()
        if not token:
            raise ValueError('runner_service_auth_unavailable')
        try:
            with self.opener.open(Request(url + '/v1/health',
                    headers={'Authorization': 'Bearer ' + token}), timeout=1) as response:
                health = json.load(response)
            if health.get('provider') != config['provider'] or health.get('status') != 'ready':
                return {'state': 'unavailable', 'can_start': False, 'reason': 'runner_identity_unverified'}
            return {'state': 'ready', 'can_start': False,
                    'remaining_turns': health.get('remaining_turns')}
        except HTTPError:
            return {'state': 'unavailable', 'can_start': False, 'reason': 'runner_identity_unverified'}
        except (URLError, TimeoutError, OSError):
            return self._offline_state()

    def _offline_state(self):
        if self.process is not None and self.process.poll() is None:
            return {'state': 'starting', 'can_start': False}
        return {'state': 'offline', 'can_start': True,
                'reason': 'runner_start_failed' if self.process is not None else None}

    def start(self, url=None):
        with self.lock:
            current = self.status(url)
            if current['state'] != 'offline' or not current['can_start']:
                return current
            config = self.config(url)
            module = 'laomedo.claude_runner' if config['provider'] == 'claude' else 'laomedo.local_runner'
            command = [sys.executable, '-m', module,
                '--state', config['state'], '--skill-store', config['skill_store'],
                '--source' if config['provider'] == 'claude' else '--source-workspace', config['source'],
                '--port', str(config['port']), '--max-model-turns', str(config['max_model_turns'])]
            if config['provider'] == 'claude':
                command.extend(['--executable', config['executable']])
            # The trusted host supplies all paths and the fixed turn ceiling.
            # Neither browser inputs nor model outputs become process arguments.
            env = service_environment(config['provider'])
            log_path = Path(config['state']) / 'service-startup.log'
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with log_path.open('ab') as log:
                self.process = subprocess.Popen(command, cwd=Path(config['state']).parent,
                    env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            return {'state': 'starting', 'can_start': False}


def install_runner_service_routes(app, authenticate, service=None):
    from fastapi import Depends, HTTPException
    from fastapi.responses import JSONResponse
    from starlette.concurrency import run_in_threadpool
    service = service or RunnerService(os.environ.get('LAOMEDO_RUNNER_SERVICE_FILE'))

    async def respond(action, url):
        try:
            value = await run_in_threadpool(action, url)
        except Exception:
            raise HTTPException(503, detail={'code': 'runner_service_configuration_unavailable'}) from None
        return JSONResponse(value, headers={'Cache-Control': 'no-store'})

    @app.get('/api/v1/laomedo/runner-service', dependencies=[Depends(authenticate)])
    async def status(url: str | None = None):
        return await respond(service.status, url)

    @app.post('/api/v1/laomedo/runner-service/start', dependencies=[Depends(authenticate)])
    async def start(url: str | None = None):
        return await respond(service.start, url)
