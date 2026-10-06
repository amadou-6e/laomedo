"""Synthetic, credential-free EXP-100 command broker. Not a production gateway."""

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
from contextlib import closing
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


MUTATIONS = {"git_push", "pr_create", "issue_create", "api_post", "graphql_mutation"}
SUPPORTED = MUTATIONS | {"git_fetch", "pr_list", "issue_list", "actions_read", "api_get", "graphql_read"}


def canonical_hash(request):
    body = {key: request.get(key) for key in ("repo", "operation", "payload")}
    return hashlib.sha256(json.dumps(body, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class Handler(BaseHTTPRequestHandler):
    server: HTTPServer

    def log_message(self, *_args):
        return

    def reply(self, status, data):
        encoded = json.dumps(data, sort_keys=True).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_POST(self):
        if self.path != "/command":
            return self.reply(404, {"error": "not_found"})
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length < 1 or length > 65536:
                return self.reply(413, {"error": "invalid_length"})
            request = json.loads(self.rfile.read(length))
            status, result = self.execute(request)
        except (ValueError, TypeError, KeyError) as error:
            status, result = 400, {"error": "bad_request", "detail": str(error)}
        self.reply(status, result)

    def execute(self, request):
        import time

        operation = request["operation"]
        if operation not in SUPPORTED:
            return 403, {"error": "unsupported_operation"}
        with closing(sqlite3.connect(self.server.db_path)) as db, db:
            db.row_factory = sqlite3.Row
            grant = db.execute("SELECT * FROM grants WHERE id=?", (request["grant"],)).fetchone()
            if grant is None or grant["revoked"] or grant["expires_at"] <= time.time():
                return 403, {"error": "grant_unavailable"}
            if request["repo"] != grant["repo"]:
                return 403, {"error": "repository_denied"}
            if operation not in json.loads(grant["operations"]):
                return 403, {"error": "operation_denied"}
            payload = request.get("payload") or {}
            if not isinstance(payload, dict):
                return 400, {"error": "invalid_payload"}
            effect_id = request.get("effect_id")
            if operation in MUTATIONS:
                if not isinstance(effect_id, str) or not effect_id:
                    return 400, {"error": "effect_id_required"}
                digest = canonical_hash(request)
                previous = db.execute("SELECT hash,state,result FROM effects WHERE grant_id=? AND id=?",
                                      (grant["id"], effect_id)).fetchone()
                if previous:
                    if previous["hash"] != digest:
                        return 409, {"error": "effect_conflict"}
                    if previous["state"] == "unknown":
                        return 202, {"state": "unknown", "resent": False}
                    return 200, {"state": "confirmed", "resent": False, "result": json.loads(previous["result"])}
                db.execute("INSERT INTO effects VALUES (?,?,?,?,NULL)",
                           (grant["id"], effect_id, digest, "unknown"))
                db.commit()  # intent is durable before sending the mutation
            result = self.perform(db, grant, operation, payload)
            if operation in MUTATIONS:
                if payload.get("simulate_lost_response"):
                    # Synthetic upstream accepted the effect; local outcome remains unknown.
                    db.commit()
                    return 202, {"state": "unknown", "resent": False}
                db.execute("UPDATE effects SET state='confirmed',result=? WHERE grant_id=? AND id=?",
                           (json.dumps(result), grant["id"], effect_id))
                db.commit()
            return 200, {"state": "confirmed", "result": result}

    def perform(self, db, grant, operation, payload):
        if operation in {"git_push", "git_fetch"}:
            # Fixed workspace/remote from the grant, never a client-provided command.
            cmd = ["git", "-C", grant["workspace"], "push" if operation == "git_push" else "fetch", "origin"]
            if operation == "git_push":
                cmd.append("HEAD:refs/heads/probe")
            completed = subprocess.run(cmd, capture_output=True, text=True, timeout=15, check=False)
            if completed.returncode:
                raise ValueError(f"git_operation_failed:{completed.returncode}")
            return {"exit_code": completed.returncode, "operation": operation}
        if operation in MUTATIONS:
            marker = payload.get("marker")
            db.execute("INSERT INTO upstream_effects(operation,marker) VALUES (?,?)", (operation, marker))
            return {"operation": operation, "marker": marker, "created": True}
        if operation in {"pr_list", "issue_list"}:
            create_op = "pr_create" if operation == "pr_list" else "issue_create"
            return {"items": [dict(row) for row in db.execute(
                "SELECT marker FROM upstream_effects WHERE operation=?", (create_op,))]}
        return {"operation": operation, "items": [], "status": 200}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", required=True)
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()
    server = HTTPServer(("127.0.0.1", args.port), Handler)
    server.db_path = str(Path(args.db).resolve())
    # A stand-in upstream credential exists only in this process, never in the
    # child/agent environment or response. No real GitHub credential is used.
    server.synthetic_upstream_secret = os.urandom(32)
    server.serve_forever()


if __name__ == "__main__":
    main()
