"""Fixed unauthenticated runner-API probe for an internal E05 stage network.

This sidecar never forwards a stage-supplied URL, header, body or credential.
It must not be launched until the amended EXP-18 protocol is reviewed.
"""

import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json


UPSTREAM_HOST = "host.docker.internal"
UPSTREAM_PORT = 8767
UPSTREAM_PATH = "/v1/runs/00000000-0000-0000-0000-000000000000"
PROBE_PATH = "/runner-auth-probe"


def probe_runner():
    connection = http.client.HTTPConnection(UPSTREAM_HOST, UPSTREAM_PORT, timeout=3)
    try:
        connection.request("GET", UPSTREAM_PATH)
        response = connection.getresponse()
        response.read(1024)
        return response.status
    finally:
        connection.close()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, _format, *_args):
        # Never retain client-controlled paths or headers in logs.
        pass

    def do_GET(self):
        if self.path != PROBE_PATH or self.headers.get("Content-Length", "0") != "0":
            self.send_error(404)
            return
        try:
            status = probe_runner()
        except (OSError, http.client.HTTPException):
            status = 502
        payload = json.dumps({"upstream_status": status}).encode("ascii")
        self.send_response(status if status == 401 else 502)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        self.send_error(405)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8098), Handler).serve_forever()
