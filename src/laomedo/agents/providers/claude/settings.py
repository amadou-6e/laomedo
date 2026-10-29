"""Feature settings and fixed protocol values; mutable state has one owner."""

from __future__ import annotations

IMAGE = "laomedo-claude-controller:2.1.310-acp0.98.0"


PROFILE = "laomedo-claude-profile"


CLI_VERSION = "2.1.310"


EXECUTION_GUARD = """import os,sys,time
remaining=min(float(sys.argv[2]),float(sys.argv[1])-time.time())
if remaining <= 0: raise SystemExit(124)
os.execvp('timeout',['timeout','--signal=TERM','--kill-after=5s',str(remaining),*sys.argv[3:]])
"""


SYSTEM = (
    "Work in /draft using the provided tools and pinned native skills. "
    "Read and edit files through the workspace command tool. Native controller "
    "file and shell tools are disabled. Only draft files may be changed. Commands execute in a separate "
    "credential-free container without network access. External GitHub effects "
    "require the scoped mediation tool or a validated downstream operation. "
    "Do not claim external changes without a successful receipt. When an output "
    "contract is provided, return exactly one JSON object without fences."
)
