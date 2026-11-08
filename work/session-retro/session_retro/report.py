"""Local source-linked review queues; candidates are not confirmed mistakes."""

import json
from pathlib import Path

from session_retro.errors import RetrospectiveError
from session_retro.index import SessionIndex
from session_retro.models import ReportResult


class RetrospectiveReport:
    """Write private review inputs without requesting models or changing rules."""

    def __init__(self, index: SessionIndex):
        """Use an already admitted private index without owning its connection."""
        self.index = index

    def write(self, directory: Path) -> ReportResult:
        """Stream messages and explicit-failure/gap candidates to private JSONL."""
        root = self.index.settings.private_root
        if root is None or not directory.resolve().is_relative_to(root.resolve()):
            raise RetrospectiveError("report_outside_private_root")
        self.index.verify()
        directory.mkdir(parents=True, exist_ok=True)
        coverage = self.index.coverage()
        (directory / "coverage.json").write_text(
            coverage.model_dump_json(indent=2), encoding="utf-8"
        )
        messages = candidates = 0
        with (
            (directory / "messages.jsonl").open("w", encoding="utf-8") as timeline,
            (directory / "candidates.jsonl").open("w", encoding="utf-8") as queue,
        ):
            for row in self.index.db.execute(
                "SELECT line,timestamp,kind,role,phase,message_id,name,call_id,turn_id,offset,length,failure,text,text_truncated FROM events ORDER BY line"
            ):
                value = dict(row)
                if row["kind"] in {"message", "message_observation"}:
                    timeline.write(json.dumps(value, ensure_ascii=False) + "\n")
                    messages += 1
                if row["failure"] == 1 or row["kind"] in {
                    "compaction",
                    "unknown",
                    "malformed",
                    "oversized",
                }:
                    queue.write(json.dumps(value, ensure_ascii=False) + "\n")
                    candidates += 1
        (directory / "README.md").write_text(
            "# Private retrospective review queue\n\nThese are indexed observations, not confirmed mistakes or root causes. Read source context with the CLI before drawing conclusions. Message observations retain duplicate native representations; do not count them as distinct requests. Coverage distinguishes indexing from analysis. No child session was opened. Redaction is best-effort; do not publish these files.\n",
            encoding="utf-8",
        )
        return ReportResult(
            directory=str(directory.resolve()), messages=messages, candidates=candidates
        )
