"""Loopback-only synthetic GitHub identity endpoint for EXP-108."""

from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread


class FakeProvider:
    def __init__(self):
        self.tokens = {}
        self.codes = {}
        self.requests = []
        self.server = None

    def add_token(self, token, *, account="alice", repositories=("org/repo",),
                  operations=("contents:write",), token_type="fine_grained",
                  expired=False):
        expiry = datetime.now(timezone.utc) + timedelta(days=-1 if expired else 1)
        self.tokens[token] = {"type": token_type, "account": account,
                              "repositories": list(repositories),
                              "operations": list(operations),
                              "expires_at": expiry.isoformat()}

    def add_code(self, code, token, state):
        self.codes[code] = (token, state)

    def __enter__(self):
        provider = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                if self.client_address[0] != "127.0.0.1":
                    self.send_error(403)
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    data = json.loads(self.rfile.read(length))
                    # Retain only route and non-secret fields.
                    provider.requests.append({"path": self.path,
                                              "repository": data.get("repository"),
                                              "operation": data.get("operation")})
                    if self.path == "/exchange":
                        issued = provider.codes.get(data.get("code"))
                        if issued and issued[1] == data.get("state"):
                            provider.codes.pop(data["code"])
                            result = {"token": issued[0]}
                        else:
                            result = None
                    elif self.path == "/verify":
                        result = provider.tokens.get(data.get("token"))
                    elif self.path == "/write":
                        token = provider.tokens.get(data.get("token"))
                        result = {"accepted": True} if (token and
                            data.get("repository") in token["repositories"] and
                            data.get("operation") in token["operations"]) else None
                    else:
                        result = None
                    if result is None:
                        self.send_error(403)
                        return
                    body = json.dumps(result).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                except (ValueError, TypeError):
                    self.send_error(400)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    @property
    def url(self):
        return f"http://127.0.0.1:{self.server.server_port}"

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
