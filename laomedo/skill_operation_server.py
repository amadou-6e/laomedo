"""Authenticated loopback boundary for Skill operations; no source/Git writes."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
from pathlib import Path
import secrets

from .skill_operations import SkillOperations
from .skill_store import SkillStore


def server(operations, token, port=8787):
    if not isinstance(token, str) or not 32 <= len(token) <= 512:
        raise ValueError('private_skill_service_required')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def reply(self, status, value):
            data = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self):
            if not secrets.compare_digest(self.headers.get('Authorization', ''), 'Bearer '+token):
                self.reply(401, {'error_category': 'unauthorized'})
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if (self.headers.get('Content-Type', '').split(';')[0] != 'application/json' or
                        not 0 < size <= 4*1024*1024):
                    raise ValueError('skill_request_invalid')
                body = json.loads(self.rfile.read(size))
                action = self.path.removeprefix('/v1/skill-operations/')
                fields = {'prepare': {'skill_id', 'revision_id', 'commit_id'},
                          'apply': {'ticket', 'operation', 'editor'},
                          'history': {'skill_id', 'revision_id', 'before'},
                          'diff': {'skill_id', 'commit_id'},
                          'compare': {'skill_id', 'commit_id', 'revision_id'}}
                if (action not in fields or self.path != '/v1/skill-operations/'+action or
                        not isinstance(body, dict) or set(body) != fields[action]):
                    raise ValueError('skill_request_invalid')
                self.reply(200, getattr(operations, action)(**body))
            except Exception:
                # Never disclose parser data, source paths, tickets or tracebacks.
                self.reply(400, {'error_category': 'skill_operation_refused'})

    return ThreadingHTTPServer(('127.0.0.1', port), Handler)


def main():
    parser = argparse.ArgumentParser()
    for field in ('registry', 'database', 'policies', 'api-token-file'):
        parser.add_argument('--'+field, type=Path, required=True)
    parser.add_argument('--port', type=int, default=8787)
    args = parser.parse_args()
    operations = SkillOperations(SkillStore(args.registry), args.database,
                                 json.loads(args.policies.read_text(encoding='utf-8')))
    server(operations, args.api_token_file.read_text().strip(), args.port).serve_forever()


if __name__ == '__main__':
    main()
