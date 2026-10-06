"""Authenticated, loopback-only fake runner for visible Stop integration tests."""

import argparse
from datetime import datetime, timezone
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
import time
from uuid import uuid4


def utc():
    return datetime.now(timezone.utc).isoformat()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8769)
    args = parser.parse_args()
    root = args.state.resolve()
    root.mkdir(parents=True, exist_ok=True)
    token_path = root / "api-token"
    if not token_path.exists():
        token_path.write_text(secrets.token_hex(32), encoding="ascii")
    token = token_path.read_text(encoding="ascii").strip()
    journal = root / "journal.jsonl"
    runs, by_request = {}, {}
    lock = threading.Lock()

    def record(kind, run_id=None, **extra):
        entry = {"kind": kind, "run_id": run_id, "at_utc": utc(),
                 "monotonic": time.monotonic(), **extra}
        with lock:
            with journal.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(entry, sort_keys=True) + "\n")

    def complete_later(run_id, seconds):
        time.sleep(seconds)
        with lock:
            run = runs[run_id]
            if run["status"] == "running":
                run["status"] = "completed"
                effect = True
            else:
                effect = False
        if effect:
            record("synthetic_effect", run_id)

    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, value):
            payload = json.dumps(value).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def auth(self):
            if not secrets.compare_digest(self.headers.get("Authorization", ""),
                                          "Bearer " + token):
                self.reply(401, {"status": "failed", "error_category": "unauthorized"})
                return False
            return True

        def do_GET(self):
            if not self.auth():
                return
            parts = self.path.strip("/").split("/")
            if len(parts) == 3 and parts[:2] == ["v1", "requests"]:
                with lock:
                    run = by_request.get(parts[2])
                    value = dict(runs[run]) if run else None
                record("request_lookup", run, found=bool(value))
                if value:
                    self.reply(200, {key: value.get(key) for key in
                        ("client_request_id", "request_hash", "run_id", "status")})
                else:
                    self.reply(404, {"error_category": "request_not_found"})
                return
            if len(parts) == 3 and parts[:2] == ["v1", "runs"]:
                with lock:
                    value = dict(runs.get(parts[2], {}))
                record("status_read", parts[2], found=bool(value))
                self.reply(200 if value else 404, value or {"status": "failed"})
                return
            self.reply(404, {"status": "failed"})

        def do_POST(self):
            if not self.auth():
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 <= length <= 65536:
                    raise ValueError()
                body = json.loads(self.rfile.read(length) or b"{}")
            except (TypeError, ValueError):
                self.reply(400, {"status": "failed", "error_category": "bad_body"})
                return
            parts = self.path.strip("/").split("/")
            if len(parts) == 4 and parts[:2] == ["v1", "runs"] and parts[3] == "cancel":
                with lock:
                    run = runs.get(parts[2])
                    if run and run["status"] in {"prepared", "running"}:
                        run["cancel_requested"] = True
                        run["cancel_confirmed"] = True
                        run["status"] = "cancelled"
                    response = dict(run) if run else None
                record("cancel_received", parts[2], known=bool(run))
                self.reply(202 if run else 404, response or {"status": "failed"})
                return
            if parts != ["v1", "runs", "async"]:
                self.reply(404, {"status": "failed"})
                return
            request_id = body.get("request_id")
            if not isinstance(request_id, str):
                self.reply(400, {"status": "failed", "error_category": "request_id_required"})
                return
            canonical = {key: value for key, value in body.items() if key != "request_id"}
            request_hash = "sha256:" + hashlib.sha256(json.dumps(
                canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False
            ).encode("utf-8")).hexdigest()
            task = str(body.get("task", ""))
            case = "A" if "CASE_A" in task else "B" if "CASE_B" in task else "CONTROL"
            with lock:
                existing = by_request.get(request_id)
                if existing:
                    run = runs[existing]
                    if run["request_hash"] != request_hash:
                        self.reply(409, {"status": "failed", "error_category": "identity_conflict"})
                        return
                else:
                    run_id = str(uuid4())
                    run = {"run_id": run_id, "status": "running", "provider": "codex",
                           "client_request_id": request_id, "request_hash": request_hash,
                           "raw_event_ref": f"laomedo:run:{run_id}:events",
                           "cancel_requested": False, "cancel_confirmed": False,
                           "requested_model": body.get("model"),
                           "requested_effort": body.get("effort"),
                           "answer": "synthetic-complete"}
                    runs[run_id] = run
                    by_request[request_id] = run_id
            record("post_received", run["run_id"], case=case, duplicate=bool(existing))
            if not existing:
                seconds = 8 if case == "A" else 6 if case == "B" else 1
                threading.Thread(target=complete_later, args=(run["run_id"], seconds),
                                 daemon=True).start()
                if case == "B":
                    record("synthetic_wait_started", run["run_id"])
            if case == "A":
                record("ack_held", run["run_id"])
                time.sleep(3)
            with lock:
                response = dict(run)
            self.reply(202, response)
            record("ack_sent", run["run_id"], case=case, status=response["status"])

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    record("server_ready", None, port=args.port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
