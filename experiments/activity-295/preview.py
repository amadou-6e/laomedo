"""Read-only activity preview: new assets, existing retained-run GET endpoints.

No login/session export, mutation forwarding, or model inference. Existing
browser authentication follows the backend's ordinary checks unchanged.
"""

from http.client import HTTPConnection
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

BUILD = Path("C:/CodeWorkspace/laomedo/.tools/activity-295-isolated-build")


class Preview(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript", ".mjs": "text/javascript", ".css": "text/css"}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BUILD), **kwargs)

    def do_GET(self):
        if "If-Modified-Since" in self.headers:
            del self.headers["If-Modified-Since"]
        path = urlsplit(self.path).path
        if path.startswith("/api/"):
            connection = HTTPConnection("127.0.0.1", 17884, timeout=30)
            headers = {
                key: value
                for key, value in self.headers.items()
                if key.lower() not in {"host", "connection", "accept-encoding"}
            }
            try:
                connection.request("GET", self.path, headers=headers)
                response = connection.getresponse()
                body = response.read()
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() not in {"connection", "transfer-encoding", "content-length", "set-cookie"}:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            finally:
                connection.close()
            return
        if not Path(self.translate_path(path)).is_file():
            self.path = "/activity295.html"
        if self.path == "/activity295.html":
            body = (BUILD / "activity295.html").read_text(encoding="utf-8").encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        super().do_GET()

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_POST(self):
        self.send_error(405, "Read-only preview; use the original app for changes")

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST

    def log_message(self, *_args):
        pass  # Never log authenticated request details.


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 55895), Preview)
    print("Read-only activity preview: http://127.0.0.1:55895", flush=True)
    server.serve_forever()
