"""Draft EXP-18 model egress sidecar, not approved for a model turn.

Accept only CONNECT api.openai.com:443. No credential is held here and no
stage-provided destination, URL, header or body is forwarded to a host service.
"""

import select
import socket
import socketserver


DESTINATION = ("api.openai.com", 443)
MAX_REQUEST = 4096


def parse_connect(data):
    """Return remaining tunnel bytes only for the one reviewed authority."""
    if len(data) > MAX_REQUEST or b"\r\n\r\n" not in data:
        raise ValueError("invalid_proxy_request")
    headers, remainder = data.split(b"\r\n\r\n", 1)
    lines = headers.split(b"\r\n")
    if lines[0] != b"CONNECT api.openai.com:443 HTTP/1.1":
        raise ValueError("unreviewed_proxy_destination")
    for line in lines[1:]:
        if b":" not in line:
            raise ValueError("invalid_proxy_header")
        name, value = line.split(b":", 1)
        name = name.strip().lower()
        if name in (b"proxy-authorization", b"content-length", b"transfer-encoding"):
            raise ValueError("proxy_auth_or_body_refused")
        if name == b"host" and value.strip() != b"api.openai.com:443":
            raise ValueError("proxy_host_mismatch")
    return remainder


class Handler(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(5)
        data = b""
        try:
            while b"\r\n\r\n" not in data and len(data) <= MAX_REQUEST:
                part = self.request.recv(min(1024, MAX_REQUEST + 1 - len(data)))
                if not part:
                    return
                data += part
            remainder = parse_connect(data)
        except (OSError, ValueError):
            self.request.sendall(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\n\r\n")
            return
        try:
            upstream = socket.create_connection(DESTINATION, timeout=10)
        except OSError:
            self.request.sendall(b"HTTP/1.1 502 Bad Gateway\r\nContent-Length: 0\r\n\r\n")
            return
        with upstream:
            self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            if remainder:
                upstream.sendall(remainder)
            self.request.settimeout(None)
            upstream.settimeout(None)
            sockets = (self.request, upstream)
            while True:
                ready, _, _ = select.select(sockets, [], [], 120)
                if not ready:
                    return
                for source in ready:
                    payload = source.recv(65536)
                    if not payload:
                        return
                    target = upstream if source is self.request else self.request
                    target.sendall(payload)


class Server(socketserver.ThreadingMixIn, socketserver.TCPServer):
    allow_reuse_address = True
    daemon_threads = True


if __name__ == "__main__":
    with Server(("0.0.0.0", 3128), Handler) as server:
        server.serve_forever()
