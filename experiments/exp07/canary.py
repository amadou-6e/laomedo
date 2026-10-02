"""Disposable external-write grant; expiry is enforced by this service."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import threading
import time
from lease import GrantLease


STATE = Path("/canary-state")
TOKEN = os.environ["CANARY_GRANT"]
LEASE = GrantLease(time.time_ns(), int(os.environ["CANARY_LEASE_NS"]))
LOCK = threading.Lock()


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != "/status":
            self.send_error(404)
            return
        events = []
        path = STATE / "events.jsonl"
        if path.exists():
            events = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        with LOCK:
            body = {"revoked": LEASE.revoked, "expired": time.time_ns() >= LEASE.expiry_ns,
                    "expiry_ns": LEASE.expiry_ns,
                    "events": events}
        data = json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if self.path not in {"/write", "/revoke", "/renew"}:
            self.send_error(404)
            return
        authorized = self.headers.get("X-Test-Grant") == TOKEN
        now = time.time_ns()
        with LOCK:
            if self.path == "/revoke" and authorized:
                LEASE.revoke()
            if self.path == "/renew" and authorized:
                accepted = LEASE.renew(now)
            else:
                accepted = authorized and LEASE.allows(now)
            if self.path == "/revoke":
                accepted = authorized
            event = {"at_ns": now, "action": self.path.removeprefix("/"),
                     "accepted": accepted, "reason": ("ok" if accepted else
                     "revoked" if LEASE.revoked else "expired" if now >= LEASE.expiry_ns else "bad_grant")}
            with (STATE / "events.jsonl").open("a", encoding="utf-8") as stream:
                stream.write(json.dumps(event) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
        self.send_response(200 if accepted else 403)
        self.end_headers()

    def log_message(self, *_args):
        pass


STATE.mkdir(parents=True, exist_ok=True)
ThreadingHTTPServer(("0.0.0.0", 8099), Handler).serve_forever()
