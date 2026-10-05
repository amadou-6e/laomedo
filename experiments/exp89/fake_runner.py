"""Disposable, synthetic HTTP runner for EXP-89; no agent/model execution."""

import argparse
from datetime import datetime, timezone
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
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    root = args.state.resolve()
    root.mkdir(parents=True, exist_ok=True)
    token_path = root / "api-token"
    if not token_path.exists():
        token_path.write_text(secrets.token_hex(32), encoding="ascii")
    token = token_path.read_text(encoding="ascii").strip()
    journal = root / "journal.jsonl"
    runs = {}
    lock = threading.Lock()

    def record(kind, run_id=None, **extra):
        entry = {"kind": kind, "run_id": run_id, "at_utc": utc(),
                 "monotonic": time.monotonic(), **extra}
        with lock:
            with journal.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(entry, sort_keys=True) + "\n")

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
            if len(parts) != 3 or parts[:2] != ["v1", "runs"]:
                self.reply(404, {"status": "failed"})
                return
            with lock:
                value = dict(runs.get(parts[2], {}))
            self.reply(200 if value else 404, value or {"status": "failed"})

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
                    if run:
                        run["cancel_requested"] = True
                        run["status"] = "cancelled"
                record("cancel_received", parts[2], known=bool(run))
                self.reply(202 if run else 404, dict(run) if run else
                           {"status": "failed", "error_category": "unknown_run"})
                return
            if parts not in (["v1", "runs"], ["v1", "runs", "async"]):
                self.reply(404, {"status": "failed"})
                return
            task = str(body.get("task", ""))
            case = "A" if "CASE_A" in task else "B" if "CASE_B" in task else "CONTROL"
            run_id = str(uuid4())
            run = {"run_id": run_id, "status": "running", "provider": "codex",
                   "client_request_id": body.get("request_id"),
                   "raw_event_ref": f"laomedo:run:{run_id}:events",
                   "cancel_requested": False, "cancel_confirmed": False,
                   "requested_model": body.get("model"),
                   "requested_effort": body.get("effort"),
                   "answer": "synthetic-complete"}
            with lock:
                runs[run_id] = run
            record("post_received", run_id, case=case,
                   operation="start" if parts[-1] == "async" else "fresh")
            if case == "A":
                record("ack_held", run_id)
                time.sleep(3)
                self.reply(202, dict(run))
                record("ack_sent", run_id)
                return
            if case == "B":
                record("synthetic_wait_started", run_id)
                time.sleep(6)
            if not run["cancel_requested"]:
                run["status"] = "completed"
                record("synthetic_effect", run_id)
            self.reply(200 if run["status"] == "completed" else 202, dict(run))
            record("response_sent", run_id, status=run["status"])

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    record("server_ready", None, port=args.port)
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
