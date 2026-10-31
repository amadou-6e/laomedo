"""Command-line entry point for laomedo.skills.interface.operations.server."""

from pathlib import Path
import argparse
import json
from laomedo.skills.operations.service import SkillOperations
from laomedo.skills.registry.store import SkillStore

from laomedo.skills.interface.operations.server import SkillOperationServer


def main():
    parser = argparse.ArgumentParser()
    for field in ("registry", "database", "policies", "api-token-file"):
        parser.add_argument("--" + field, type=Path, required=True)
    parser.add_argument("--port", type=int, default=8787)
    args = parser.parse_args()
    operations = SkillOperations(
        SkillStore(args.registry),
        args.database,
        json.loads(args.policies.read_text(encoding="utf-8")),
    )
    SkillOperationServer(
        operations, args.api_token_file.read_text().strip(), args.port
    ).serve_forever()


if __name__ == "__main__":
    main()
