"""Locate public bundled skill instructions in the pinned, credential-free CLI."""

from pathlib import Path
import json


def main():
    source = Path(
        "/usr/local/lib/node_modules/@anthropic-ai/claude-code/bin/claude.exe"
    ).read_bytes()
    for pattern in (
        b"name: verify",
        b"name: claude-api",
        b"# Verification",
        b'"verify",menuDescription',
        b'"verify",description',
    ):
        offset = source.find(pattern)
        print(
            json.dumps(
                {
                    "pattern": pattern.decode(),
                    "offset": offset,
                    "context": (
                        source[max(0, offset - 100) : offset + 4500].decode(
                            "utf-8", errors="replace"
                        )
                        if offset >= 0
                        else None
                    ),
                }
            )
        )


if __name__ == "__main__":
    main()
