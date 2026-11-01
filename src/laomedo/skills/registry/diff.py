"""Generate exact review patches for admitted registry file inventories."""

from __future__ import annotations

import difflib


def patch_for(base: dict[str, bytes], draft: dict[str, bytes]) -> str:
    chunks = []
    for relative in sorted(base.keys() | draft.keys()):
        if base.get(relative) == draft.get(relative):
            continue
        try:
            before = base.get(relative, b"").decode("utf-8")
            after = draft.get(relative, b"").decode("utf-8")
        except UnicodeDecodeError:
            chunks.append(f"--- base/{relative}\n+++ draft/{relative}\n")
            chunks.append(f"-bytes {base.get(relative, b'')!r}\n")
            chunks.append(f"+bytes {draft.get(relative, b'')!r}\n")
            continue

        def exact_lines(value: str) -> list[str]:
            return [
                line.encode("unicode_escape").decode("ascii") + "\n"
                for line in value.splitlines(keepends=True)
            ]

        chunks.extend(
            difflib.unified_diff(
                exact_lines(before),
                exact_lines(after),
                fromfile="base/" + relative,
                tofile="draft/" + relative,
            )
        )
    return "".join(chunks)
