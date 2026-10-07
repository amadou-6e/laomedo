"""Independent lease service for exact runner containers and scoped write grants.

The operator starts this service separately from the runner. The runner never
spawns it, so a whole-process-tree termination of the runner cannot reach it.
Runners register exact container leases in the service's private state
directory and refresh a heartbeat file. On a stale heartbeat the service first
revokes every write grant bound to that lease, then stops only the labelled
container recorded in the lease, and writes a timed, durable result.

The grant endpoint is a synthetic external-write target: it accepts a write
only while the bearer grant is active. It models the revocation boundary a
real push-credential broker must provide; it is not a GitHub credential.
"""

from __future__ import annotations

import argparse
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
import time

from .container_lease import cleanup_after_loss, inspect_exact


LOSS_SECONDS = 5.0
SERVICE_STALE_SECONDS = 3.0
GRANT_TTL_SECONDS = 60.0
POLL_SECONDS = 0.25


def _write_json(path: Path, value: dict) -> None:
    pending = path.with_name(path.name + ".pending-" + secrets.token_hex(4))
    pending.write_text(json.dumps(value, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(pending, path)


def _read_json(path: Path) -> dict | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _read_float(path: Path) -> float | None:
    try:
        return float(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


class GrantBook:
    """Thread-safe registry of run-scoped synthetic write grants."""

    def __init__(self, events: Path):
        self.lock = threading.Lock()
        self.by_digest: dict[str, dict] = {}
        self.events = events

    def issue(self, token: str, now: float) -> tuple[str, str]:
        secret = secrets.token_hex(32)
        grant_id = "grant-" + secrets.token_hex(8)
        with self.lock:
            self.by_digest[sha256(secret.encode()).hexdigest()] = {
                "grant_id": grant_id, "lease_token": token,
                "expires_at": now + GRANT_TTL_SECONDS, "revoked_at": None}
        return grant_id, secret

    def renew(self, token: str, now: float) -> None:
        with self.lock:
            for grant in self.by_digest.values():
                if grant["lease_token"] == token and grant["revoked_at"] is None:
                    grant["expires_at"] = now + GRANT_TTL_SECONDS

    def revoke(self, token: str, now: float) -> list[str]:
        revoked = []
        with self.lock:
            for grant in self.by_digest.values():
                if grant["lease_token"] == token and grant["revoked_at"] is None:
                    grant["revoked_at"] = now
                    revoked.append(grant["grant_id"])
        return revoked

    def check(self, secret: str) -> tuple[bool, str | None]:
        now = time.time()
        with self.lock:
            grant = self.by_digest.get(sha256(secret.encode()).hexdigest())
            accepted = (grant is not None and grant["revoked_at"] is None and
                        now < grant["expires_at"])
            grant_id = grant["grant_id"] if grant else None
            with self.events.open("a", encoding="utf-8") as log:
                log.write(json.dumps({"at": now, "grant_id": grant_id,
                                      "accepted": accepted}) + "\n")
        return accepted, grant_id


def _handler(book: GrantBook):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            supplied = self.headers.get("Authorization", "")
            accepted = False
            if self.path == "/write" and supplied.startswith("Bearer "):
                accepted, _ = book.check(supplied[len("Bearer "):])
            body = json.dumps({"accepted": accepted}).encode()
            self.send_response(200 if accepted else 403)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


class LeaseService:
    def __init__(self, state: Path, *, port: int = 0, host: str = "127.0.0.1",
                 loss_seconds: float = LOSS_SECONDS, cleanup=cleanup_after_loss):
        self.state = state.resolve()
        (self.state / "leases").mkdir(parents=True, exist_ok=True)
        self.loss_seconds = loss_seconds
        self.cleanup = cleanup
        self.book = GrantBook(self.state / "grant-events.jsonl")
        self.server = ThreadingHTTPServer((host, port), _handler(self.book))
        self.instance = secrets.token_hex(8)
        self.stopping = threading.Event()

    @property
    def port(self) -> int:
        return self.server.server_address[1]

    def _beat(self) -> None:
        while not self.stopping.is_set():
            (self.state / "service.alive").write_text(repr(time.time()), encoding="utf-8")
            self.stopping.wait(1)

    def _accept(self, lease_dir: Path, lease: dict, now: float) -> None:
        grant_id, secret = self.book.issue(lease["token"], now)
        # The secret file is private to the runner's user and never logged.
        (lease_dir / "grant.secret").write_text(secret, encoding="utf-8")
        _write_json(lease_dir / "accepted.json", {
            "instance": self.instance, "token": lease["token"], "grant_id": grant_id,
            "accepted_at": now})

    def _finish(self, lease_dir: Path, lease: dict, reason: str, now: float) -> None:
        revoked = self.book.revoke(lease["token"], now)
        revoked_at = time.time()
        if reason == "done":
            state, _ = inspect_exact(lease["name"], lease["run_id"], lease["token"])
            verified, detail = state == "absent", state
        else:
            verified, detail = self.cleanup(lease["name"], lease["run_id"], lease["token"])
        _write_json(lease_dir / "result.json", {
            "reason": reason, "revoked_grants": revoked, "detected_at": now,
            "revoked_at": revoked_at, "cleanup_finished_at": time.time(),
            "cleanup_verified": verified, "state": detail})

    def tick(self) -> None:
        now = time.time()
        for lease_dir in sorted((self.state / "leases").iterdir()):
            if not lease_dir.is_dir() or (lease_dir / "result.json").exists():
                continue
            lease = _read_json(lease_dir / "lease.json")
            if (lease is None or lease.get("token") != lease_dir.name or
                    not all(isinstance(lease.get(k), str) and lease[k]
                            for k in ("token", "run_id", "name"))):
                continue
            if not (lease_dir / "accepted.json").exists():
                self._accept(lease_dir, lease, now)
                continue
            if (lease_dir / "done").exists():
                self._finish(lease_dir, lease, "done", now)
                continue
            beat = _read_float(lease_dir / "heartbeat")
            if beat is None or now - beat > self.loss_seconds:
                self._finish(lease_dir, lease, "heartbeat_lost", now)
            else:
                self.book.renew(lease["token"], now)

    def serve(self) -> None:
        _write_json(self.state / "service.json", {
            "pid": os.getpid(), "port": self.port, "instance": self.instance,
            "started_at": time.time()})
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        threading.Thread(target=self._beat, daemon=True).start()
        try:
            while not self.stopping.is_set():
                self.tick()
                self.stopping.wait(POLL_SECONDS)
        finally:
            self.server.shutdown()
            self.server.server_close()


class LeaseClient:
    """Runner-side registration and heartbeat for one exact container lease."""

    def __init__(self, service_state: Path, *, run_id: str, name: str, token: str,
                 cancelled: threading.Event, accept_timeout: float = 5.0):
        self.state = Path(service_state).resolve()
        info = _read_json(self.state / "service.json")
        alive = _read_float(self.state / "service.alive")
        if (info is None or alive is None or
                time.time() - alive > SERVICE_STALE_SECONDS or info.get("pid") == os.getpid()):
            raise RuntimeError("lease_service_unavailable")
        self.instance = info.get("instance")
        self.port = info.get("port")
        self.dir = self.state / "leases" / token
        self.dir.mkdir(parents=True, exist_ok=False)
        self.lost = threading.Event()
        self.stop_event = threading.Event()
        (self.dir / "heartbeat").write_text(repr(time.time()), encoding="utf-8")
        _write_json(self.dir / "lease.json", {
            "token": token, "run_id": run_id, "name": name,
            "runner_pid": os.getpid(), "created_at": time.time()})
        deadline = time.monotonic() + accept_timeout
        accepted = None
        while time.monotonic() < deadline:
            accepted = _read_json(self.dir / "accepted.json")
            if accepted is not None:
                break
            time.sleep(.05)
        if (accepted is None or accepted.get("token") != token or
                accepted.get("instance") != self.instance):
            raise RuntimeError("lease_service_did_not_accept")
        self.grant_id = accepted["grant_id"]

        def heartbeat() -> None:
            while not self.stop_event.wait(1):
                (self.dir / "heartbeat").write_text(repr(time.time()), encoding="utf-8")
                alive_at = _read_float(self.state / "service.alive")
                if alive_at is None or time.time() - alive_at > SERVICE_STALE_SECONDS:
                    self.lost.set()
                    cancelled.set()

        self.thread = threading.Thread(target=heartbeat, daemon=True)
        self.thread.start()

    def grant_secret(self) -> str:
        return (self.dir / "grant.secret").read_text(encoding="utf-8")

    def finish(self, *, timeout: float = 15.0) -> dict:
        """Report a normal end after the runner verified its own cleanup."""
        self.stop_event.set()
        self.thread.join(timeout=3)
        (self.dir / "done").write_text("done", encoding="utf-8")
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            result = _read_json(self.dir / "result.json")
            if result is not None:
                if (self.lost.is_set() or result.get("reason") != "done" or
                        result.get("cleanup_verified") is not True):
                    raise RuntimeError("lease_service_unverified")
                return result
            time.sleep(.05)
        raise RuntimeError("lease_service_unverified")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    serve = commands.add_parser("serve", help="run the independent lease service")
    serve.add_argument("--state", type=Path, required=True)
    serve.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    LeaseService(args.state, port=args.port).serve()


if __name__ == "__main__":
    main()
