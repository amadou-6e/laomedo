"""Diagnose the isolated preview supervisor startup without native work."""

import faulthandler, json, os, runpy, sys
from pathlib import Path

ROOT = Path("C:/CodeWorkspace/laomedo")
meta = json.loads((ROOT / ".tools/assistant-291-live.json").read_text())
state = Path(meta["state"]) / "lease"
sys.path.insert(0, str(ROOT / ".tools/worktrees/assistant-tools-293/src"))
faulthandler.dump_traceback_later(20, repeat=False)
sys.argv = ["lease", "serve", "--state", str(state)]
runpy.run_module("laomedo.host.leases.service_cli", run_name="__main__")
