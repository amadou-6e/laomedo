"""Bounded synthetic GitHub provider shared by independent paired states."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import threading
from urllib.parse import urlsplit
from laomedo.github_rest_transport import ISSUE_GRAPHQL_QUERY

REPOSITORY = 'example/disposable'
TOKEN = 'synthetic-paired-host-only'


class Response(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *_): self.close()


class Provider:
    def __init__(self, head_sha, *, attempt_cap=100, write_cap=5):
        self.head_sha = head_sha
        self.calls, self.prs, self.issues = [], {}, {
            9: {'number': 9, 'title': 'Existing issue', 'body': 'Existing body'}}
        self.attempt_cap, self.write_cap = attempt_cap, write_cap
        self.drop_next_patch = False
        self.lock = threading.Lock()

    @property
    def writes(self):
        return sum(call['write'] for call in self.calls)

    def handle(self, method, path, body, authorization):
        with self.lock:
            if authorization not in {'Bearer ' + TOKEN, 'token ' + TOKEN}:
                return 403, {'message': 'synthetic credential required'}
            is_write = method in {'POST', 'PATCH'} and path != '/graphql'
            if len(self.calls) >= self.attempt_cap or (is_write and self.writes >= self.write_cap):
                raise RuntimeError('provider_budget_exhausted_no_retry')
            self.calls.append({'method': method, 'path': path, 'write': is_write})
            prefix = '/repos/' + REPOSITORY
            if path == '/graphql' and method == 'POST':
                if body != {'query': ISSUE_GRAPHQL_QUERY,
                            'variables': {'owner': 'example', 'name': 'disposable'}}:
                    return 422, {'message': 'fixed query required'}
                return 200, {'data': {'repository': {'issues': {'nodes': list(self.issues.values())}}}}
            if not path.startswith(prefix + '/'):
                return 404, {'message': 'synthetic repository not found'}
            tail = path[len(prefix):]
            if tail == '/pulls' and method == 'POST':
                if not isinstance(body, dict) or not {'title', 'body', 'head', 'base'} <= body.keys():
                    return 422, {'message': 'fixture PR invalid'}
                number = 7 + len(self.prs)
                self.prs[number] = {'number': number, 'state': 'open', 'title': body['title'],
                    'body': body['body'], 'base': {'ref': body['base']}, 'head': {
                        'repo': {'full_name': REPOSITORY}, 'ref': body['head'],
                        'sha': self.head_sha(body['head'])}}
                return 201, self.prs[number]
            if tail == '/pulls' and method == 'GET':
                return 200, list(self.prs.values())
            if tail.startswith('/pulls/'):
                try: pr = self.prs[int(tail.split('/')[-1])]
                except (KeyError, ValueError): return 404, {'message': 'PR absent'}
                pr['head']['sha'] = self.head_sha(pr['head']['ref'])
                if method == 'PATCH':
                    pr.update({key: body[key] for key in ('title', 'body') if key in body})
                    if 'base' in body: pr['base'] = {'ref': body['base']}
                    if self.drop_next_patch:
                        self.drop_next_patch = False
                        return None, None  # applied, response deliberately lost
                elif method != 'GET': return 422, {'message': 'method refused'}
                return 200, pr
            if tail == '/issues' and method == 'POST':
                if not isinstance(body, dict) or set(body) != {'title', 'body'}:
                    return 422, {'message': 'issue invalid'}
                number = 9 + len(self.issues)
                self.issues[number] = {'number': number, **body}
                return 201, self.issues[number]
            if tail == '/issues' and method == 'GET':
                return 200, list(self.issues.values())
            if tail.startswith('/issues/') and method == 'GET':
                try: return 200, self.issues[int(tail.split('/')[-1])]
                except (KeyError, ValueError): return 404, {'message': 'issue absent'}
            if tail == '/actions/runs' and method == 'GET':
                return 200, {'total_count': 1, 'workflow_runs': [{'id': 21, 'status': 'completed'}]}
            if tail == '/actions/jobs/21' and method == 'GET':
                return 200, {'id': 21, 'status': 'completed', 'conclusion': 'success'}
            return 404, {'message': 'fixture path unsupported'}

    def open(self, request, timeout):
        code, value = self.handle(request.get_method(), urlsplit(request.full_url).path,
            json.loads(request.data) if request.data else None, request.get_header('Authorization'))
        if code is None: raise OSError('synthetic_response_lost')
        if code >= 400:
            from urllib.error import HTTPError
            raise HTTPError(request.full_url, code, 'synthetic rejection', {}, None)
        return Response(json.dumps(value).encode())

    def serve(self):
        provider = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_): pass
            def dispatch(self):
                self.connection.settimeout(15)
                encoding = self.headers.get('Transfer-Encoding')
                if encoding == 'chunked' and self.headers.get('Content-Length') is None:
                    chunks = bytearray()
                    while True:
                        line = self.rfile.readline(128)
                        if not line.endswith(b'\r\n') or b';' in line:
                            self.send_error(400); return
                        size = int(line.strip(), 16)
                        if size < 0 or size + len(chunks) > 65536:
                            self.send_error(413); return
                        if size == 0:
                            if self.rfile.readline(128) != b'\r\n': self.send_error(400); return
                            break
                        chunks.extend(self.rfile.read(size))
                        if self.rfile.read(2) != b'\r\n': self.send_error(400); return
                    raw = bytes(chunks)
                elif encoding is None:
                    length = int(self.headers.get('Content-Length', '0'))
                    if length < 0 or length > 65536: self.send_error(413); return
                    raw = self.rfile.read(length)
                else:
                    self.send_error(400); return
                body = json.loads(raw) if raw else None
                code, value = provider.handle(self.command, urlsplit(self.path).path, body,
                                              self.headers.get('Authorization'))
                if code is None:
                    self.close_connection = True
                    return
                encoded = json.dumps(value).encode()
                self.send_response(code)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(encoded)))
                self.end_headers(); self.wfile.write(encoded)
            do_GET = do_POST = do_PATCH = dispatch
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server
