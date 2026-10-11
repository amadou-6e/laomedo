"""Zero-write local gh-api feasibility check; never campaign acceptance evidence."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import shutil
import subprocess
import tempfile
import threading


def dry_run():
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_GET(self):
            calls.append({'method': 'GET', 'path': self.path})
            valid = (self.path == '/repos/example/disposable/issues' and
                     self.headers.get('Authorization') in {
                         'token synthetic-loopback-only', 'Bearer synthetic-loopback-only'})
            body = json.dumps([{'number': 9, 'title': 'Fixture', 'body': 'Fixture body'}]
                              if valid else {'message': 'fixture target refused'}).encode()
            self.send_response(200 if valid else 403)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            calls.append({'method': 'POST', 'path': self.path})
            self.send_error(403, 'writes not permitted in feasibility check')

    executable = shutil.which('gh')
    if executable is None:
        raise RuntimeError('direct_gh_unavailable')
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with tempfile.TemporaryDirectory(prefix='laomedo-gh-zero-write-') as folder:
            environment = {key: value for key, value in os.environ.items()
                           if not key.upper().startswith(('GH_', 'GITHUB_', 'GIT_', 'GCM_', 'LAOMEDO_'))
                           and key.upper() not in {'GH', 'GH_LAOMEDO'}}
            environment.update({'GH_CONFIG_DIR': folder, 'GH_ENTERPRISE_TOKEN': 'synthetic-loopback-only',
                'GH_NO_UPDATE_NOTIFIER': '1', 'GH_NO_EXTENSION_UPDATE_NOTIFIER': '1',
                'GH_PROMPT_DISABLED': '1', 'GIT_CONFIG_GLOBAL': os.devnull,
                'GIT_CONFIG_NOSYSTEM': '1', 'GIT_TERMINAL_PROMPT': '0'})
            command = [executable, 'api',
                f'http://127.0.0.1:{server.server_port}/repos/example/disposable/issues', '--method', 'GET']
            observed = subprocess.run(command, cwd=folder, env=environment, timeout=15,
                                      capture_output=True)
            value = json.loads(observed.stdout) if observed.returncode == 0 else None
            passed = (observed.returncode == 0 and isinstance(value, list) and
                      value[0]['number'] == 9 and calls == [{
                          'method': 'GET', 'path': '/repos/example/disposable/issues'}])
            return {'development_only': True, 'status': 'passed' if passed else 'failed',
                    'exit_code': observed.returncode, 'calls': calls,
                    'actual_writes': 0, 'real_credentials': 0, 'model_turns': 0,
                    'stderr_category': 'empty' if not observed.stderr else 'nonempty'}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


if __name__ == '__main__':
    print(json.dumps(dry_run(), sort_keys=True))
