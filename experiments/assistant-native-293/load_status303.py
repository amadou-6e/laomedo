"""Zero-turn native resume diagnosis; never prompt or rewrite the run record."""

import asyncio
import json
from pathlib import Path
import tempfile
import sys
import os

from laomedo.agents.agents.codex.controller.models import CodexLaunch
from laomedo.agents.agents.codex.controller.models import SplitPolicy
from laomedo.agents.agents.codex.runtime import CodexAgentRuntime
from laomedo.agents.agents.base.acp.session import AcpSession


async def main():
    record_path = Path(os.environ["LAOMEDO_ACCEPTANCE_RUN_RECORD"])
    record = json.loads(record_path.read_text(encoding="utf-8"))
    original = AcpSession._request

    async def observed(self, request, method, seconds):
        print("request", method, flush=True)
        try:
            return await asyncio.wait_for(request, timeout=seconds)
        except Exception as error:
            print("failed", method, type(error).__name__, flush=True)
            text = str(error).lower()
            print("known_diagnostic_terms", [term for term in ("not found", "cwd", "directory", "thread", "session", "mcp", "config", "model", "auth", "expired", "unauthorized", "sandbox", "executor", "environment", "policy") if term in text], flush=True)
            print("error_fields", list(vars(error)), flush=True)
            raise

    AcpSession._request = observed
    root = Path(tempfile.mkdtemp(prefix="laomedo-resume303-"))
    for name in ("workspace", "canonical", "store"):
        (root / name).mkdir()
    options = {}
    if "--session-login" in sys.argv:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "docker-boundary-277"))
        from acceptance import session_login
        login = session_login()
        options["split"] = SplitPolicy(provider_config=login["split_provider_config"], access_token=login["split_access_token"])
    runtime = CodexAgentRuntime(CodexLaunch(workspace=root / "workspace", canonical=root / "canonical", store_mount=root / "store", image=record["image_id"], managed_image=True), root, lifetime_seconds=120, **options)
    try:
        await runtime.initialize()
        await runtime.models()
        await runtime.open(record, resume=True)
        print("native_load_passed_without_prompt", flush=True)
    finally:
        await runtime.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as error:
        print("diagnostic_failed", type(error).__name__)
        raise SystemExit(1)
