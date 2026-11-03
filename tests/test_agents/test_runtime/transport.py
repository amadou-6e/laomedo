"""Internal ACP transport double; never real-provider acceptance."""


class FakeServer:
    @property
    def streams_closed(self):
        return (
            getattr(self, "reader", None) is not None
            and getattr(self, "stderr_reader", None) is not None
            and not self.reader.is_alive()
            and not self.stderr_reader.is_alive()
        )

    calls = []
    turn_inputs = []

    def _write(self, data):
        self.process.stdin.write(data)
        self.process.stdin.flush()

    def __init__(self, command, evidence):
        self.command = command
        self.evidence = evidence
        self.events = []
        self.resume = False
        self.log = (evidence / "raw-events.jsonl").open("a", encoding="utf-8")
        self.log.write('{"method":"initialized"}\n')
        self.log.flush()
        self.calls.append(command)

    def request(self, method, params, timeout=30):
        if method == "initialize":
            return {"result": {}}
        if method == "model/list":
            return {
                "result": {
                    "data": [{"id": "test-model", "supportedReasoningEfforts": ["low"]}]
                }
            }
        if method == "thread/start":
            return {"result": {"thread": {"id": "native-thread"}}}
        if method == "thread/resume":
            self.resume = True
            assert params["threadId"] == "native-thread"
            return {"result": {"thread": {"id": "native-thread"}}}
        if method == "turn/start":
            self.turn_inputs.append(params["input"][0]["text"])
            return {"result": {"turn": {"id": "turn-2" if self.resume else "turn-1"}}}
        raise AssertionError(method)

    def notify(self, method, params):
        pass

    def wait_turn(self, turn_id, timeout, cancelled):
        workspace = self.evidence / "workspace"
        if self.resume:
            assert (workspace / "agent.txt").read_text() == "from-first-turn"
        else:
            assert not (workspace / "agent.txt").exists()
            (workspace / "agent.txt").write_text("from-first-turn")
        self.events.append(
            {
                "method": "item/completed",
                "params": {
                    "item": {"type": "agentMessage", "text": "synthetic answer"}
                },
            }
        )
        self.log.write('{"method":"turn/completed"}\n')
        self.log.flush()
        return "completed", None

    async def initialize(self):
        self.request("initialize", {})

    async def models(self):
        reply = self.request("model/list", {})
        return [
            {"id": item["id"], "efforts": item["supportedReasoningEfforts"]}
            for item in reply["result"]["data"]
        ]

    async def open(self, record, *, resume):
        self.active_thread_id = "native-thread"
        self.output_requirements = record.get("output_requirements")
        self.precheck_call_count = 0
        self.verified_precheck_calls = set()
        params = {"threadId": "native-thread"} if resume else {}
        if self.output_requirements:
            from laomedo.agents.interface.output.utils import dynamic_tool

            params["dynamicTools"] = [dynamic_tool(self.output_requirements)]
        self.request("thread/resume" if resume else "thread/start", params)
        return "native-thread"

    def assert_controller_isolated(self):
        pass

    async def prompt(self, text, *, skills, seconds, cancelled):
        # Fixture-only hooks preserve the existing domain test scenarios. No
        # production component offers these retired native request/wait methods.
        from laomedo.agents.agents.codex.controller.models import CodexTurn

        sent = self.request(
            "turn/start",
            {"threadId": "native-thread", "input": [{"type": "text", "text": text}]},
        )
        identity = sent["result"]["turn"]["id"]
        status, error = self.wait_turn(identity, seconds, cancelled)
        return CodexTurn(turn_id=identity, status=status, error=error)

    async def close(self):
        self.log.close()
