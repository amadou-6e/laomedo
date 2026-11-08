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
            r"""(?im)((?:["']?[\w-]*(?:token|password|secret|api[_-]?key)[\w-]*["']?)\s*[:=]\s*)(["'])([^\r\n]*?)\2""",
            r'\1"[REDACTED]"',
            value,
        )
        return re.sub(
            r"(?im)^(\s*[A-Z_]*(?:TOKEN|PASSWORD|SECRET|API_KEY)[A-Z_]*\s*=)[^\r\n]*",
            r"\1[REDACTED]",
            value,
        )
