"""Command-line entry point for laomedo.skills.operations.server."""

from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
import argparse
import json
import laomedo.skills.operations.service as _operations_service
import laomedo.skills.registry.store as _registry_store
import secrets

from laomedo.skills.operations.server import SkillOperationServer


def main():
    parser = argparse.ArgumentParser()
    for field in ("registry", "database", "policies", "api-token-file"):
        parser.add_argument("--" + field, type=Path, required=True)
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    operations = _operations_service.SkillOperations(
        _registry_store.SkillStore(args.registry),
        args.database,
        json.loads(args.policies.read_text(encoding="utf-8")),
    )
    SkillOperationServer(
        operations, args.api_token_file.read_text().strip(), args.port
    ).serve_forever()


if __name__ == "__main__":
    main()
