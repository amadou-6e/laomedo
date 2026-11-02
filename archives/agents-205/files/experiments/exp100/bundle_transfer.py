"""Credential-free, local EXP-100/S2 bundle verifier; not a product transport.

Only the host-selected baseline source and expected ref enter the trusted
side. Bundle bytes are agent-controlled. This deliberately never pushes.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import signal
import subprocess
import tempfile


SHA = re.compile(rb"[0-9a-f]{40}\Z")
MAX_BUNDLE_BYTES = 4 * 1024 * 1024
GIT_TIMEOUT_SECONDS = 10


def git_env(*, home: Path | None = None, trace: str | None = None) -> dict[str, str]:
    """Discard inherited Git, GitHub and credential-manager authority."""
    keep = ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "TMP", "TEMP", "TMPDIR")
    env = {key: value for key, value in os.environ.items() if key in keep}
    env.update({"GIT_CONFIG_GLOBAL": os.devnull,
                "GIT_CONFIG_SYSTEM": os.devnull,
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_TERMINAL_PROMPT": "0",
                "GIT_NO_REPLACE_OBJECTS": "1", "GIT_OPTIONAL_LOCKS": "0",
                "GIT_LFS_SKIP_SMUDGE": "1"})
    if trace is not None:
        env["GIT_TRACE"] = trace
    if home is not None:
        env.update({"HOME": str(home), "USERPROFILE": str(home),
                    "XDG_CONFIG_HOME": str(home)})
    return env


def git(args: list[str], *, directory: Path | None = None,
        env: dict[str, str] | None = None) -> subprocess.CompletedProcess[bytes]:
    command = ["git"]
    if directory is not None:
        command.extend(["-C", str(directory)])
    command.extend(args)
    options = {"stdin": subprocess.DEVNULL, "stdout": subprocess.PIPE,
               "stderr": subprocess.PIPE,
               "env": env if env is not None else git_env()}
    if os.name == "nt":
        options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
    else:
        options["start_new_session"] = True
    with tempfile.TemporaryDirectory(prefix="laomedo-exp100-home-") as home:
        isolated = options["env"].copy()
        if "HOME" not in isolated:
            isolated.update({"HOME": home, "USERPROFILE": home,
                             "XDG_CONFIG_HOME": home})
        options["env"] = isolated
        process = subprocess.Popen(command, **options)
        try:
            stdout, stderr = process.communicate(timeout=GIT_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired as error:
            killed = False
            if os.name == "nt":
                outcome = subprocess.run(["taskkill", "/PID", str(process.pid),
                                          "/T", "/F"], check=False,
                                         stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, timeout=5)
                killed = outcome.returncode == 0
            else:
                os.killpg(process.pid, signal.SIGKILL)
                killed = True
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                killed = False
            raise RuntimeError("git_timeout_cleanup_verified" if killed else
                               "git_timeout_cleanup_unverified") from error
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)


def _header(data: bytes, expected_ref: str) -> tuple[str, bytes | None, list[bytes]]:
    """Inspect only the bundle header; leave pack integrity to unbundle."""
    end = data.find(b"\n\n")
    if end < 0 or end > 4096 or not data.startswith(b"# v"):
        return "bundle_invalid", None, []
    lines = data[:end].split(b"\n")
    if lines[0] not in (b"# v2 git bundle", b"# v3 git bundle"):
        return "bundle_version", None, []
    version = lines[0]
    if version == b"# v2 git bundle" and any(line.startswith(b"@") for line in lines[1:]):
        return "bundle_version", None, []
    if any(line.startswith(b"@filter=") for line in lines[1:]):
        return "bundle_version", None, []
    formats = [line for line in lines[1:] if line.startswith(b"@object-format=")]
    if formats and formats != [b"@object-format=sha1"]:
        return "object_format", None, []
    if any(line.startswith(b"@") and line not in (b"@object-format=sha1",)
           for line in lines[1:]):
        return "bundle_version", None, []
    prerequisites = [line[1:].split(b" ", 1)[0] for line in lines[1:]
                     if line.startswith(b"-")]
    if any(not SHA.fullmatch(value) for value in prerequisites):
        return "bundle_invalid", None, []
    refs = [line.split(b" ", 1) for line in lines[1:]
            if line and not line.startswith((b"-", b"@"))]
    if len(refs) != 1 or len(refs[0]) != 2 or not SHA.fullmatch(refs[0][0]):
        return "ref_count", None, []
    if refs[0][1] != expected_ref.encode("ascii"):
        return "ref_name", None, []
    return "accepted", refs[0][0], prerequisites


def verify_bundle(data: bytes, *, trusted_source: Path, baseline: str,
                  expected_ref: str, confirmed_commit: str | None = None) -> dict:
    """Import and classify one untrusted bundle in a private bare repository.

    `confirmed_commit` is a trusted host-journal value, never a value read
    from the bundle. The caller must bind it to this run before this call.
    """
    result = {"reason": "bundle_invalid", "stage": "header", "commit": None,
              "tree": None}
    if not isinstance(data, bytes) or len(data) > MAX_BUNDLE_BYTES or \
            not re.fullmatch(r"refs/heads/[A-Za-z0-9._/-]+", expected_ref) or \
            not re.fullmatch(r"[0-9a-f]{40}", baseline):
        return result
    reason, commit, prerequisites = _header(data, expected_ref)
    if reason != "accepted":
        result["reason"] = reason
        return result
    with tempfile.TemporaryDirectory(prefix="laomedo-exp100-s2-") as root:
        stage = Path(root) / "stage.git"
        bundle = Path(root) / "agent.bundle"
        bundle.write_bytes(data)
        if git(["init", "--bare", "--quiet", str(stage)]).returncode:
            result.update(reason="object_invalid", stage="seed")
            return result
        seed = git(["fetch", "--no-tags", str(trusted_source), baseline], directory=stage)
        if seed.returncode:
            result.update(reason="object_invalid", stage="seed")
            return result
        if confirmed_commit is not None:
            if not re.fullmatch(r"[0-9a-f]{40}", confirmed_commit):
                result.update(reason="object_invalid", stage="seed")
                return result
            seed_confirmed = git(["fetch", "--no-tags", str(trusted_source),
                                  confirmed_commit], directory=stage)
            if seed_confirmed.returncode:
                result.update(reason="object_invalid", stage="seed")
                return result
        for prerequisite in prerequisites:
            if git(["cat-file", "-e", prerequisite.decode() + "^{commit}"],
                   directory=stage).returncode:
                result.update(reason="missing_prerequisite", stage="prerequisite")
                return result
        imported = git(["bundle", "unbundle", str(bundle)], directory=stage)
        if imported.returncode:
            result.update(reason="object_invalid", stage="import")
            return result
        fsck = git(["fsck", "--strict", "--no-reflogs", commit.decode("ascii")],
                   directory=stage)
        if fsck.returncode:
            result.update(reason="object_invalid", stage="integrity")
            return result
        object_id = commit.decode("ascii")
        kind = git(["cat-file", "-t", object_id], directory=stage)
        if kind.returncode or kind.stdout.strip() != b"commit":
            result.update(reason="ref_type", stage="type")
            return result
        if git(["merge-base", "--is-ancestor", baseline, object_id],
               directory=stage).returncode:
            result.update(reason="baseline_ancestry", stage="ancestry")
            return result
        changed = git(["diff", "--no-ext-diff", "--no-textconv", "--name-only",
                       "-z", "--no-renames", baseline, object_id], directory=stage)
        if changed.returncode:
            result.update(reason="object_invalid", stage="diff")
            return result
        if any(path.startswith(b".github/workflows/") for path in
               changed.stdout.split(b"\0")):
            result.update(reason="workflow_change", stage="workflow")
            return result
        tree = git(["rev-parse", object_id + "^{tree}"], directory=stage)
        if tree.returncode:
            result.update(reason="object_invalid", stage="tree")
            return result
        result.update(reason="accepted", stage="complete", commit=object_id,
                      tree=tree.stdout.decode("ascii").strip())
        return result
