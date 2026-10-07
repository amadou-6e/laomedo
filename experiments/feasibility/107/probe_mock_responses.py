"""Credential-free mock Responses stream for a Codex app-server tool probe."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import time
from uuid import uuid4


class MockResponses:
    def __init__(self, tool_input=None, before_first_output=None,
                 tool_request_numbers=(1,)):
        self.requests = []
        self.tool_input = tool_input
        self.before_first_output = before_first_output
        self.tool_request_numbers = frozenset(tool_request_numbers)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def do_POST(self):
                if self.path != "/v1/responses":
                    self.send_error(404)
                    return
                length = int(self.headers.get("Content-Length", "0"))
                request = json.loads(self.rfile.read(length))
                owner.requests.append({"model": request.get("model"),
                                       "advertised_tools": sorted({
                                           child.get("name")
                                           for item in request.get("input", [])
                                           if isinstance(item, dict) and
                                           item.get("type") == "additional_tools"
                                           for group in item.get("tools", [])
                                           for child in group.get("tools", [])
                                           if isinstance(child, dict) and
                                           isinstance(child.get("name"), str)}),
                                       "input_types": [item.get("type") for item
                                                       in request.get("input", [])
                                                       if isinstance(item, dict)],
                                       "tool_outputs": [str(item.get("output", ""))[:2000]
                                                        for item in request.get("input", [])
                                                        if isinstance(item, dict) and
                                                        item.get("type") ==
                                                        "custom_tool_call_output"]})
                if len(owner.requests) == 1 and owner.before_first_output:
                    owner.before_first_output()
                response_id = "resp_" + uuid4().hex
                if (owner.tool_input is not None and
                        len(owner.requests) in owner.tool_request_numbers):
                    item = {"id": "ctc_" + uuid4().hex,
                            "type": "custom_tool_call", "status": "completed",
                            "call_id": "call_" + uuid4().hex,
                            "namespace": "functions", "name": "exec",
                            "input": owner.tool_input}
                else:
                    item = {"id": "msg_" + uuid4().hex, "type": "message",
                            "status": "completed", "role": "assistant",
                            "content": [{"type": "output_text",
                                         "text": "SYNTHETIC_READY",
                                         "annotations": []}]}
                base = {"id": response_id, "object": "response",
                        "created_at": int(time.time()),
                        "model": request.get("model"), "output": [],
                        "status": "in_progress", "error": None,
                        "incomplete_details": None, "instructions": None,
                        "parallel_tool_calls": False, "tool_choice": "auto",
                        "tools": [], "usage": None}
                completed = {**base, "status": "completed", "output": [item],
                             "usage": {"input_tokens": 1, "output_tokens": 1,
                                       "total_tokens": 2}}
                events = [
                    {"type": "response.created", "response": base},
                    {"type": "response.output_item.added", "output_index": 0,
                     "item": {**item, "status": "in_progress"}},
                    {"type": "response.output_item.done", "output_index": 0,
                     "item": item},
                    {"type": "response.completed", "response": completed},
                ]
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.end_headers()
                for number, event in enumerate(events):
                    event["sequence_number"] = number
                    self.wfile.write(("event: " + event["type"] + "\n" +
                                      "data: " + json.dumps(event) + "\n\n").encode())
                    self.wfile.flush()

        self.server = ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    @property
    def base_url(self):
        return f"http://host.docker.internal:{self.server.server_port}/v1"
