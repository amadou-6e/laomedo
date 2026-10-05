"""No-model, loopback-only runner that records a delayed external effect."""

from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import time
from uuid import uuid4


EVENTS = Path("/state/runner-events.jsonl")
DELAYS = {"control": 0.2, "client": 4.0, "component": 5.0, "server": 6.0}


def record(case: str, event: str) -> None:
    row = json.dumps({"case": case, "event": event,
                      "utc": datetime.now(timezone.utc).isoformat(),
                      "monotonic": time.monotonic()}, sort_keys=True) + "\n"
    fd = os.open(EVENTS, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    try:
        os.write(fd, row.encode("utf-8"))
        os.fsync(fd)
    finally:
        os.close(fd)


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args) -> None:
        pass

    def do_POST(self) -> None:
        if self.path != "/v1/runs":
            self.send_error(404)
            return
        try:
            size = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(size))
            case = str(payload["task"])
            if case not in DELAYS or self.headers.get("Authorization") != "Bearer synthetic-exp10-token":
                self.send_error(400)
                return
        except (ValueError, KeyError, TypeError):
            self.send_error(400)
            return
        record(case, "entered")
        time.sleep(DELAYS[case])
        record(case, "effect")
        result = {
            "run_id": str(uuid4()), "status": "completed", "answer": "synthetic-effect",
            "requested_model": "synthetic", "requested_effort": "none",
            "skill": {"revision_id": "sha256:" + "a" * 64, "use_evidence": "offered"},
            "raw_event_ref": "synthetic:exp10",
        }
        data = json.dumps(result).encode("utf-8")
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            record(case, "response_written")
        except (BrokenPipeError, ConnectionResetError):
            record(case, "response_disconnected")


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 18740), Handler).serve_forever()
