"""Private loopback acceptance relay; request bodies are checked, never retained."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import requests


class TaskPayloadHandler(BaseHTTPRequestHandler):
    """Forward authenticated calls to one fixed owned runner without logging."""

    def do_GET(self):
        self._forward()

    def do_POST(self):
        self._forward()

    def _forward(self):
        if not self.path.startswith("/v1/"):
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 <= length <= 2 * 1024 * 1024:
            self.send_error(413)
            return
        body = self.rfile.read(length) if length else None
        if self.command == "POST" and self.path in ("/v1/runs", "/v1/runs/async"):
            self.server.task_requests += 1
            self.server.canary_leaked |= self.server.canary in (body or b"")
        response = requests.request(
            self.command,
            self.server.upstream + self.path,
            data=body,
            headers={
                "Authorization": self.headers.get("Authorization", ""),
                "Content-Type": "application/json",
            },
            timeout=120,
        )
        self.send_response(response.status_code)
        self.send_header(
            "Content-Type", response.headers.get("Content-Type", "application/json")
        )
        self.send_header("Content-Length", str(len(response.content)))
        self.end_headers()
        self.wfile.write(response.content)

    def log_message(self, *args):
        return None


class TaskPayloadProxy(ThreadingHTTPServer):
    """Observe the actual forwarded task bytes without exposing the canary."""

    daemon_threads = True

    def __init__(self, upstream, canary):
        self.upstream = upstream
        self.canary = canary.encode()
        self.task_requests = 0
        self.canary_leaked = False
        super().__init__(("127.0.0.1", 0), TaskPayloadHandler)
