"""Structural guards: callers must use public owner methods, not internal state."""

from pathlib import Path
import re
import unittest

SOURCE_ROOT = Path(__file__).resolve().parents[3] / "src" / "laomedo"

# Modules that own the state they touch. Callers outside this set must go
# through public methods such as GitHubConnectionService.read_access_token,
# GitHubRunAuthority.run_for_job and GitHubRunAuthority.worker_remaining.
OWNERS = {
    "github/connections/service.py",
    "github/connections/run_authority.py",
    # Provisioning serializes its own sessions with the service commit lock.
    # This is a known residual of the same defect class; see the README.
    "github/connections/provisioning.py",
}

FORBIDDEN_STATE_READS = (
    re.compile(r"\bauthority\.(runs|jobs|workers|clock)\b"),
    re.compile(r"\b(?:self|authority)\.connections\.(?:journal|commit_lock)\b"),
    # A bare `connections.` attribute read; module paths such as
    # `laomedo.github.connections.journal` are excluded by the dot lookbehind.
    re.compile(r"(?<![\w.])connections\.(?:journal|commit_lock)\b"),
    re.compile(r"\._credential\("),
)

PRIVATE_AUTHENTICATION_IMPORT = re.compile(
    r"authentication\.connections import \(?[^)]*\b_\w+", re.S
)


def _sources():
    """Yield (relative path, text) for every package module outside owners."""
    for path in sorted(SOURCE_ROOT.rglob("*.py")):
        relative = path.relative_to(SOURCE_ROOT).as_posix()
        if relative in OWNERS:
            continue
        yield relative, path.read_text(encoding="utf-8")


class ConnectionBoundaryTests(unittest.TestCase):
    """Refuse direct reads of connection-service and authority internals."""

    def test_no_module_reads_authority_or_connection_internals(self):
        offenders = [
            (relative, pattern.pattern)
            for relative, text in _sources()
            for pattern in FORBIDDEN_STATE_READS
            if pattern.search(text)
        ]
        self.assertEqual(offenders, [])

    def test_no_module_imports_private_authentication_helpers(self):
        offenders = [
            relative
            for relative, text in _sources()
            if PRIVATE_AUTHENTICATION_IMPORT.search(text)
        ]
        self.assertEqual(offenders, [])

    def test_owner_exemptions_remain_the_only_direct_state_owners(self):
        """Every exemption must still exist, so the allowlist cannot silently rot."""
        for relative in OWNERS:
            self.assertTrue((SOURCE_ROOT / relative).is_file(), relative)
