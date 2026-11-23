"""Acquire registered skill images; reuse the owner-authorized private ACL repair."""

from pathlib import Path

from laomedo.docker import DockerRuntime
from laomedo.host.private_state.windows import WindowsDirectorySecurity
import win32api
import win32security
import win32con
import sys


def main():
    if sys.argv[1:] == ["codex"]:
        from laomedo.agents.agents.codex.settings import IMAGE
    elif sys.argv[1:] == ["worker"]:
        from laomedo.agents.agents.opencode.settings import WORKER_IMAGE

        IMAGE = WORKER_IMAGE
    elif not sys.argv[1:]:
        from laomedo.agents.agents.claude.settings import IMAGE
    else:
        raise SystemExit("Expected no argument, codex or worker")
    token = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(), win32con.TOKEN_QUERY
    )
    sid = win32security.ConvertSidToStringSid(
        win32security.GetTokenInformation(token, win32security.TokenUser)[0]
    )
    security = WindowsDirectorySecurity()
    state = Path.home() / ".laomedo-image-builds"
    security.restrict(state, sid)
    security.verify(state, sid)
    with DockerRuntime(environment=None).client() as client:
        print(DockerRuntime.ensure_image(client, IMAGE), flush=True)


if __name__ == "__main__":
    main()
