"""Credential-free helper/PATH and sandbox DNS controls, no provider calls."""
import json
from pathlib import Path
import subprocess
import tempfile
import threading
from http.server import HTTPServer; from http.server import BaseHTTPRequestHandler
from experiments.exp139.bindings import PROFILE_OVERRIDES

ROOT = Path(__file__).resolve().parents[2]
IMAGE = 'sha256:eceda79a349c46a8afd6fb271e92b979f872ca67cbdf228fde6dee0856481e78'


class RejectOnly(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(404)
        self.end_headers()

    def log_message(self, *args):
        pass


def probe():
    server = HTTPServer(('127.0.0.1', 0), RejectOnly)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    results = []
    try:
        url = f'http://host.docker.internal:{server.server_port}/no-credential-probe'
        with tempfile.TemporaryDirectory(prefix='laomedo139-helper-') as temporary:
            root = Path(temporary)
            config = root / 'config.toml'
            config.write_bytes((ROOT / 'src/laomedo/agents/resources/runner-config.toml').read_bytes())
            helper = root / 'bin'
            helper.mkdir()
            (helper / 'git-remote-laomedo').write_text('#!/bin/sh\nprintf HELPER_FOUND\\n\n', newline='\n')
            prefix = ['docker', 'run', '--rm', '--pull=never', '--network', 'bridge', '--user', '10001:10001',
                '--mount', f'type=bind,source={config},target=/config.toml,readonly',
                '--mount', f'type=bind,source={helper},target=/run/laomedo/bin,readonly',
                '--env', 'PATH=/run/laomedo/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
                '--entrypoint', 'sh', IMAGE, '-c',
                'mkdir -p /home/runner/.codex; cp /config.toml /home/runner/.codex/config.toml; '
                'export CODEX_HOME=/home/runner/.codex; exec "$@"', 'bootstrap']
            fetch = ['node', '-e', f"fetch('{url}').then(r=>console.log(r.status)).catch(e=>console.log(e.cause?.code||e.name))"]
            cases = (
                ('plain_shell', ['bash', '-c', 'command -v git-remote-laomedo']),
                ('login_shell', ['bash', '-lc', 'command -v git-remote-laomedo']),
                ('git_explicit_exec_path', ['git', '--exec-path=/run/laomedo/bin', 'remote-laomedo']),
                ('mediator_without_sandbox', fetch),
                ('mediator_inside_sandbox', ['codex', *PROFILE_OVERRIDES, 'sandbox', '-P', 'container-edit', '--', *fetch]))
            for mode, command in cases:
                result = subprocess.run(prefix + command, input=b'', capture_output=True, timeout=20)
                text = result.stdout.decode(errors='replace')
                results.append({'mode': mode, 'exit_code': result.returncode,
                    'helper_found': 'HELPER_FOUND' in text or 'git-remote-laomedo' in text,
                    'http_status': 404 if '404' in text else None,
                    'network_error': [code for code in ('EPERM', 'EACCES', 'ENETUNREACH', 'ECONNREFUSED', 'EAI_AGAIN', 'ENOTFOUND') if code in text],
                    'model_turns': 0, 'provider_writes': 0})
    finally:
        server.shutdown()
        server.server_close()
    return {'fixture': 'temporary_404_server_and_dummy_helper', 'controls': results,
            'model_turns': 0, 'provider_writes': 0}


if __name__ == '__main__':
    result = probe()
    Path(__file__).with_name('HELPER-CONTROL.json').write_bytes((json.dumps(result, indent=2, sort_keys=True) + '\n').encode())
    print(json.dumps(result))
