"""Credential-owning mediator HTTP process, separate from lease supervision.

The host application must supply a reviewed transport and start this as an
independent process. This class intentionally has no ambient `gh` fallback or
credential-loading CLI. A real scoped identity is a separate deployment gate.
"""

from __future__ import annotations

import argparse
from http.server import ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import threading
import time

from .github_mediation import MediationStore
from .github_git_transport import (GitHubGitTransport, GitHubMediatedTransport,
                                   PushOutcomeUnknown)
from .github_rest_transport import GitHubRestTransport
from .host_token_connection import HostTokenConnection
from .lease_service import _handler


class MediationHTTPService:
    def __init__(self, store: MediationStore, transport, *, host="127.0.0.1", port=0):
        if transport is None:
            raise ValueError("credential_transport_required")
        self.instance = secrets.token_hex(16)
        self.server = ThreadingHTTPServer((host, port),
                                          _handler(None, store, transport, self.instance))

    @property
    def port(self):
        return self.server.server_address[1]

    def serve(self):
        self.server.serve_forever()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class JournaledTransport:
    """Private, non-secret provider-attempt journal for diagnostic accounting."""

    def __init__(self, transport, path: Path,
                 diagnostic_path: Path | None = None):
        self.transport = transport
        self.path = path
        self.diagnostic_path = diagnostic_path
        self.lock = threading.Lock()

    def __call__(self, repository, operation, payload, **binding):
        event = {"at_wall": time.time(), "at_monotonic": time.monotonic(),
                 "repository": repository, "operation": operation}
        if operation == "git_push":
            event.update({"branch": payload.get("branch"),
                          "commit": payload.get("commit")})
        with self.lock, self.path.open("a", encoding="utf-8") as journal:
            journal.write(json.dumps(event, sort_keys=True) + "\n")
        try:
            return self.transport(repository, operation, payload, **binding)
        except PushOutcomeUnknown as failure:
            if self.diagnostic_path is not None:
                diagnostic = {"at_wall": time.time(), "operation": "git_push",
                              "category": failure.category,
                              "exit_code": failure.exit_code}
                with self.lock, self.diagnostic_path.open("a", encoding="utf-8") as journal:
                    journal.write(json.dumps(diagnostic, sort_keys=True) + "\n")
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state", type=Path, required=True,
                        help="private host-only state directory, never an agent mount")
    parser.add_argument("--repository", required=True)
    parser.add_argument("--checkout", type=Path, required=True,
                        help="trusted host checkout containing the exact commit")
    parser.add_argument("--baseline", required=True,
                        help="pinned baseline SHA for workflow-file classification")
    parser.add_argument("--agent-mount", type=Path, required=True,
                        help="source tree mounted or copied into the agent")
    parser.add_argument("--connection-id", required=True)
    parser.add_argument("--connection-generation", type=int, required=True)
    parser.add_argument("--token-file", type=Path, required=True)
    parser.add_argument("--token-key", default="GH")
    args = parser.parse_args()
    state = args.state.resolve()
    state.mkdir(parents=True, exist_ok=True)
    connection = HostTokenConnection(
        connection_id=args.connection_id,
        generation=args.connection_generation,
        repository=args.repository, token_file=args.token_file,
        key=args.token_key, forbidden_mount=args.agent_mount)
    git_transport = GitHubGitTransport(args.repository, args.checkout,
                                       args.baseline, connection.token)
    rest_transport = GitHubRestTransport(args.repository, connection.token)
    store = MediationStore(
        state / "mediator.sqlite",
        workflow_change_classifier=git_transport.classify_workflow_diff,
        connection_is_current=connection.current)
    transport = GitHubMediatedTransport(git_transport, rest_transport)
    service = MediationHTTPService(
        store, JournaledTransport(transport, state / "provider-attempts.jsonl",
                                  state / "push-diagnostics.jsonl"))
    # This file contains no token, only the instance/port required by a
    # trusted controller. It is never copied into a run workspace.
    status = state / "mediator.json"
    pending = status.with_suffix(".pending")
    pending.write_text(json.dumps({"pid": os.getpid(), "port": service.port,
                                   "instance": service.instance,
                                   "started_at": time.time(),
                                   "connection_id": args.connection_id,
                                   "generation": args.connection_generation,
                                   "repository": args.repository}) + "\n",
                       encoding="utf-8")
    os.replace(pending, status)
    try:
        service.serve()
    finally:
        service.close()


if __name__ == "__main__":
    main()
