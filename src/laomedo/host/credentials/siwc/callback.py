"""Handle the single local browser authentication callback."""

from http.server import BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlsplit


class CallbackHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, received, **kwargs):
        self.received = received
        super().__init__(*args, **kwargs)

    def log_message(self, *_args):
        pass

    def do_GET(self):
        parts = urlsplit(self.path)
        if parts.path != "/auth/callback":
            self.send_error(404)
            return
        for key, values in parse_qs(parts.query).items():
            if len(values) == 1:
                self.received[key] = values[0]
        body = b"Laomedo received the ChatGPT response. You may close this tab."
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
