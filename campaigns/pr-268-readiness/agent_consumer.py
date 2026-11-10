"""Native scheduler probe using internal fake provider controls; no live acceptance."""
import asyncio
import importlib.util
import unittest
from pathlib import Path
from lfx.graph.graph.base import Graph

ROOT = Path("C:/CodeWorkspace/laomedo/.tools/worktrees/pr-268")
SPEC = importlib.util.spec_from_file_location("feedback_tests", ROOT / "tests/test_github/test_pull_requests/test_graph/test_feedback.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

class AgentConsumerProbe(MODULE.PRAgentLoopTests):
    async def test_extra_consumer(self):
        flow = MODULE.builder.build()
        consumer = MODULE.builder.node(ROOT / "tests/test_github/test_pull_requests/test_graph/result.py", "consumer", {}, 900, 0)
        flow["data"]["nodes"].append(consumer)
        flow["data"]["edges"].append(MODULE.builder.edge(flow["data"]["nodes"][1], "operation", consumer, "result"))
        graph = Graph.from_payload(flow)
        try:
            result = await asyncio.wait_for(graph.arun(inputs=[{}], outputs=["pr", "consumer"]), timeout=25)
            print("RESULT", str(result))
        finally:
            print("COUNTS", len(self.agent_calls), len(self.fake.writes))

if __name__ == "__main__":
    unittest.main(defaultTest="AgentConsumerProbe.test_extra_consumer")
