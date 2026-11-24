"""Own the lifecycle of one loopback HTTP server for internal controls."""

from threading import Thread
from http.server import BaseHTTPRequestHandler
import json


class RunningHTTPServer:
    """Start and fully release only the server supplied by the caller."""

    def __init__(self, server):
        """Retain the caller's unstarted server without opening other resources."""
        self.server = server
        self.thread = Thread(
            target=lambda: server.serve_forever(poll_interval=0.05), daemon=True
        )

    def __enter__(self):
        """Start the owned thread and return the supplied server for requests."""
        self.thread.start()
        return self.server

    def __exit__(self, *_):
        """Close the socket and join the owned thread, or report incomplete cleanup."""
        try:
            if self.thread.ident is not None:
                self.server.shutdown()
        finally:
            self.server.server_close()
            if self.thread.ident is not None:
                self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise RuntimeError("Owned HTTP server thread did not stop")


class RecordingJSONHandler(BaseHTTPRequestHandler):
    """Return caller-supplied internal test data; record no headers or secrets."""

    def do_GET(self):
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 <= length <= 1024 * 1024:
            self.send_error(413)
            return
        if length:
            self.rfile.read(length)
        self.server.requests.append((self.command, self.path))
        if self.server.redirect:
            self.send_response(302)
            self.send_header("Location", self.server.redirect)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(getattr(self.server, "response_status", 200))
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(self.server.payload).encode())

    do_POST = do_GET

    def log_message(self, *_):
        pass
