"""Check current transport callers against actual retained runners; no dispatch."""

import json
import os
import sys
import unittest
from pathlib import Path


def main():
    import langflow

    root = Path("C:/CodeWorkspace/laomedo")
    evidence = root / "claude-review.local/agents-250-20261107"
    if "--agents" in sys.argv:
        suite = unittest.defaultTestLoader.discover(
            "tests/test_agents", top_level_dir="tests"
        )
    elif "--langflow" in sys.argv:
        names = [
            "test_langflow.test_codex_component",
            "test_langflow.test_claude_component",
            "test_langflow.test_opencode_component",
            "test_langflow.test_handoff_graph",
            "test_langflow.test_integrated_contract",
            "test_langflow_join_http",
            "test_langflow_join_service",
            "test_shared.test_http.test_redirects",
        ]
        suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    else:
        from laomedo.agents.interface.bridge import HttpAgentBridge
        from laomedo.agents.interface.langflow.component import _HTTP
        from urllib.request import Request

        state = Path(json.loads((evidence / "runtime-path.json").read_text())["path"])
        results = []
        for provider, port in [
            ("codex", 18815),
            ("claude", 18816),
            ("opencode", 18817),
        ]:
            run = json.loads(
                (evidence / (provider + "-actual-stop-result.json")).read_text()
            )
            run_id = run["run_id"]
            token = state / provider / "api-token"
            bridge = HttpAgentBridge(
                {provider: f"http://127.0.0.1:{port}"}, {provider: token}
            )
            status = bridge.status(provider, run_id)
            req = Request(
                f"http://127.0.0.1:{port}/v1/runs/{run_id}",
                headers=bridge._headers(provider),
            )
            with _HTTP.open(req, timeout=10) as response:
                direct = json.load(response)
            assert status["status"] == direct["status"] == "cancelled"
            assert status["cancel_confirmed"] is direct["cancel_confirmed"] is True
            results.append(
                {
                    "provider": provider,
                    "run_id": run_id,
                    "shared_bridge_status": status["status"],
                    "agent_transport_status": direct["status"],
                    "cancel_confirmed": True,
                    "new_model_submission": False,
                }
            )
        (evidence / "real-transport-reads.json").write_text(
            json.dumps(results, indent=2) + "\n"
        )
        print(
            "Three real retained runs read through both current authenticated transports; no model dispatch."
        )
        return
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())


if __name__ == "__main__":
    main()
