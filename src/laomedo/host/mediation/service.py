"""Credential-owning mediator HTTP process, separate from lease supervision.

The host application must supply a reviewed transport and start this as an
independent process. This class intentionally has no ambient `gh` fallback or
credential-loading CLI. A real scoped identity is a separate deployment gate."""

from __future__ import annotations

import laomedo.host.leases.server as _leases_server
from pathlib import Path
import json
import laomedo.github.transport.git.errors as _git_errors
import laomedo.host.leases.utils as _leases_utils
import laomedo.host.mediation.store as _mediation_store
import secrets
import threading
import time


class MediationHTTPService:
    def __init__(
        self,
        store: _mediation_store.MediationStore,
        transport,
        *,
        host="127.0.0.1",
        port=0,
    ):
        if transport is None:
            raise ValueError("credential_transport_required")
        self.instance = secrets.token_hex(16)
        self.server = _leases_server.LeaseHTTPServer(
            None, store, transport, self.instance, host=host, port=port
        )

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

    def __init__(self, transport, path: Path, diagnostic_path: Path | None = None):
        self.transport = transport
        self.path = path
        self.diagnostic_path = diagnostic_path
        self.lock = threading.Lock()

    def __call__(self, repository, operation, payload, **binding):
        event = {
            "at_wall": time.time(),
            "at_monotonic": time.monotonic(),
            "repository": repository,
            "operation": operation,
        }
        if operation == "git_push":
            event.update(
                {"branch": payload.get("branch"), "commit": payload.get("commit")}
            )
        with self.lock, self.path.open("a", encoding="utf-8") as journal:
            journal.write(json.dumps(event, sort_keys=True) + "\n")
        try:
            return self.transport(repository, operation, payload, **binding)
        except _git_errors.PushOutcomeUnknown as failure:
            if self.diagnostic_path is not None:
                diagnostic = {
                    "at_wall": time.time(),
                    "operation": "git_push",
                    "category": failure.category,
                    "exit_code": failure.exit_code,
                }
                with (
                    self.lock,
                    self.diagnostic_path.open("a", encoding="utf-8") as journal,
                ):
                    journal.write(json.dumps(diagnostic, sort_keys=True) + "\n")
            raise
