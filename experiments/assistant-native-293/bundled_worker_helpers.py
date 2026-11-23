"""Check public helper access under the worker home mount, without credentials."""

import subprocess

from laomedo.agents.agents.codex.settings import IMAGE


def main():
    result = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "--network",
            "none",
            "--read-only",
            "--tmpfs",
            "/home/runner/.codex:rw,uid=10001,gid=10001,mode=0700",
            IMAGE,
            "sh",
            "-c",
            "mkdir -p /home/runner/.codex/skills && "
            "ln -s /opt/acp/system-skills /home/runner/.codex/skills/.system && "
            "test -r /home/runner/.codex/skills/.system/skill-creator/scripts/quick_validate.py && "
            "test ! -w /home/runner/.codex/skills/.system/skill-creator/SKILL.md && "
            "python3 -c 'import yaml; print(\"public helper readable; immutable; YAML available\")'",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    print(result.stdout.strip())


if __name__ == "__main__":
    main()
