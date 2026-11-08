"""Chronological source windows, without claiming each window is a separate task."""

from pathlib import Path

from session_retro.index import SessionIndex
from session_retro.models import Episode


class EpisodeBuilder:
    """Group records after original user messages using one streaming SQL cursor."""

    def __init__(self, index: SessionIndex):
        """Borrow an admitted private index; caller retains its connection."""
        self.index = index

    def write(self, path: Path) -> int:
        """Write private bounded user-message windows with native outcome locations."""
        episode = None
        count = 0
        with path.open("w", encoding="utf-8") as output:
            rows = self.index.db.execute(
                "SELECT line,kind,role,phase,turn_id,failure,CASE WHEN kind='message' AND role='user' THEN text ELSE '' END AS text,text_truncated FROM events ORDER BY line"
            )
            for row in rows:
                if row["kind"] == "message" and row["role"] == "user":
                    if episode is not None:
                        episode.end_line = row["line"] - 1
                        output.write(episode.model_dump_json() + "\n")
                        count += 1
                    episode = Episode(
                        id=f"user-{row['line']}",
                        source_kind=self._source_kind(row["text"]),
                        start_line=row["line"],
                        end_line=row["line"],
                        turn_id=row["turn_id"],
                        user_text=row["text"],
                        user_text_truncated=bool(row["text_truncated"]),
                    )
                if episode is None:
                    continue
                episode.end_line = row["line"]
                episode.calls += row["kind"] == "call"
                episode.results += row["kind"] == "result"
                episode.explicit_failure_records += row["failure"] == 1
                episode.compactions += row["kind"] == "compaction"
                if (
                    row["kind"] == "message"
                    and row["role"] == "assistant"
                    and row["phase"] in {"final_answer", "final"}
                ):
                    episode.final_answer_lines.append(row["line"])
            if episode is not None:
                output.write(episode.model_dump_json() + "\n")
                count += 1
        return count

    def _source_kind(self, text: str) -> str:
        """Classify explicit wrapper forms without inferring task independence."""
        text = text.lstrip()
        if text.startswith(
            (
                "<environment_context>",
                "<external_codex_apps_open_page>",
                "# AGENTS.md instructions",
            )
        ):
            return "injected_context"
        return (
            "clarification"
            if text.startswith("<send_user_message_question_reply>")
            else "request_or_continuation"
        )
