"""Best-effort secret masking for private search/read views, not publication."""

import re


class Redactor:
    """Mask recognizable credentials; arbitrary sensitive prose can still remain."""

    def text(self, value: str) -> str:
        """Return masked text without logging the original or changing source bytes."""
        value = re.sub(
            r"\b(?:gh[pousr]_[A-Za-z0-9_]{12,}|github_pat_[A-Za-z0-9_]{12,}|sk-[A-Za-z0-9_-]{12,}|eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)",
            "[REDACTED_CREDENTIAL]",
            value,
        )
        value = re.sub(r"(?i)(bearer\s+)[A-Za-z0-9._~+/=-]+", r"\1[REDACTED]", value)
        value = re.sub(
            r"""(?m)(?<![\w-])((["']?)([\w-]{1,256})\2[ \t]*[:=][ \t]*)(["'])([^\r\n]*?)\4""",
            self._quoted_assignment,
            value,
        )
        return re.sub(
            r"(?im)^([ \t]*([A-Z_][A-Z0-9_]{0,255})[ \t]*=)[^\r\n]*",
            self._environment_assignment,
            value,
        )

    def _quoted_assignment(self, match: re.Match) -> str:
        """Inspect one bounded key instead of retrying a keyword regex per suffix."""
        if self._sensitive(match[3]):
            return match[1] + match[4] + "[REDACTED]" + match[4]
        return match[0]

    def _environment_assignment(self, match: re.Match) -> str:
        """Mask an environment assignment only when its complete key is sensitive."""
        return match[1] + "[REDACTED]" if self._sensitive(match[2]) else match[0]

    @staticmethod
    def _sensitive(key: str) -> bool:
        """Classify a bounded key; unusually long/unrecognized secrets remain gaps."""
        normalized = key.lower().replace("_", "").replace("-", "")
        return any(
            word in normalized for word in ("token", "password", "secret", "apikey")
        )
