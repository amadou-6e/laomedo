"""Command-line entry point for laomedo.skills.sources.server."""

from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
from pathlib import Path
import argparse
import json
import laomedo.skills.sources.errors as _sources_errors
import laomedo.skills.sources.service as _sources_service
import secrets

from laomedo.skills.sources.server import SkillSourceServer


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--allow-local-root", type=Path, action="append", default=[])
    parser.add_argument("--api-token-file", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8782)
    args = parser.parse_args()
    sources = _sources_service.SkillSources(
        args.registry, args.state, args.allow_local_root
    )
    token = args.api_token_file.read_text(encoding="utf-8").strip()
    SkillSourceServer(sources, token, port=args.port).serve_forever()


if __name__ == "__main__":
    main()
