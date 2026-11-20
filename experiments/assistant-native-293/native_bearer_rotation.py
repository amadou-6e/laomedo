"""Pinned native same-thread bearer refresh against a loopback fake Responses API.

No real account, provider request or model quota is used. Run inside the built
controller image with --network none and an owner-only credential tmpfs.
"""

import http.server
import json
from pathlib import Path
import queue
import subprocess
import threading
import time

headers = []


class Responses(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        headers.append(self.headers.get("Authorization"))
        item = {
            "id": "msg_fixture",
            "type": "message",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": "ROTATED", "annotations": []}],
        }
        response = {
            "id": "resp_fixture",
            "object": "response",
            "model": "gpt-6.1-sol",
            "status": "completed",
            "output": [item],
            "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
        }
        events = [
            {
                "type": "response.created",
                "response": {**response, "status": "in_progress", "output": []},
            },
            {
                "type": "response.output_item.added",
                "output_index": 0,
                "item": {**item, "status": "in_progress", "content": []},
            },
            {
                "type": "response.output_text.delta",
                "item_id": "msg_fixture",
                "output_index": 0,
                "content_index": 0,
                "delta": "ROTATED",
            },
            {"type": "response.output_item.done", "output_index": 0, "item": item},
            {"type": "response.completed", "response": response},
        ]
        body = "".join(
            "event: " + e["type"] + "\ndata: " + json.dumps(e) + "\n\n" for e in events
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        return


server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Responses)
threading.Thread(target=server.serve_forever, daemon=True).start()
credential = Path("/tmp/laomedo-provider-auth/access-token")
credential.write_text("fixture-original-token", encoding="utf-8")
credential.chmod(0o600)
config = [
    'model_provider="fixture"',
    'model_providers.fixture.name="Local fixture"',
    f'model_providers.fixture.base_url="http://127.0.0.1:{server.server_port}/v1"',
    'model_providers.fixture.auth.command="/bin/cat"',
    'model_providers.fixture.auth.args=["/tmp/laomedo-provider-auth/access-token"]',
    'model_providers.fixture.auth.cwd="/"',
    "model_providers.fixture.auth.refresh_interval_ms=1",
    "model_providers.fixture.auth.timeout_ms=1000",
    "model_providers.fixture.requires_openai_auth=false",
    "model_providers.fixture.supports_websockets=false",
    'model_providers.fixture.wire_api="responses"',
]
command = ["codex"]
for setting in config:
    command.extend(["-c", setting])
command.extend(["app-server", "--listen", "stdio://"])
process = subprocess.Popen(
    command,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    text=True,
)
messages = queue.Queue()


def read():
    for line in process.stdout:
        try:
            messages.put(json.loads(line))
        except ValueError:
            pass


threading.Thread(target=read, daemon=True).start()


def send(method, params, identifier=None):
    value = {"method": method, "params": params}
    if identifier is not None:
        value["id"] = identifier
    process.stdin.write(json.dumps(value) + "\n")
    process.stdin.flush()


def wait(predicate):
    deadline = time.monotonic() + 45
    while time.monotonic() < deadline:
        value = messages.get(timeout=max(0.01, deadline - time.monotonic()))
        if predicate(value):
            return value
    raise TimeoutError("native response not observed")


try:
    send(
        "initialize",
        {
            "clientInfo": {
                "name": "laomedo-offline-check",
                "title": "Laomedo offline check",
                "version": "1",
            },
            "capabilities": {"experimentalApi": True},
        },
        1,
    )
    assert "result" in wait(lambda v: v.get("id") == 1)
    send("initialized", {})
    send(
        "thread/start",
        {
            "model": "gpt-6.1-sol",
            "cwd": "/draft",
            "approvalPolicy": "never",
            "sandbox": "read-only",
        },
        2,
    )
    opened = wait(lambda v: v.get("id") == 2)
    thread = opened["result"]["thread"]["id"]
    credential.write_text("fixture-renewed-token", encoding="utf-8")
    time.sleep(0.002)
    send(
        "turn/start",
        {"threadId": thread, "input": [{"type": "text", "text": "Reply ROTATED"}]},
        3,
    )
    started = wait(lambda v: v.get("id") == 3)
    assert "result" in started
    finished = wait(lambda v: v.get("method") == "turn/completed")
    assert finished["params"]["threadId"] == thread
    assert finished["params"]["turn"]["status"] == "completed"
    assert headers and all(h == "Bearer fixture-renewed-token" for h in headers)
    credential.write_text("fixture-later-token", encoding="utf-8")
    time.sleep(0.002)
    send(
        "turn/start",
        {
            "threadId": thread,
            "input": [{"type": "text", "text": "Reply ROTATED again"}],
        },
        4,
    )
    assert "result" in wait(lambda v: v.get("id") == 4)
    second = wait(lambda v: v.get("method") == "turn/completed")
    assert second["params"]["threadId"] == thread
    assert second["params"]["turn"]["status"] == "completed"
    assert headers == ["Bearer fixture-renewed-token", "Bearer fixture-later-token"]
    print(
        json.dumps(
            {
                "same_thread": True,
                "native_turns_completed": 2,
                "renewed_bearer_used": True,
                "requests": len(headers),
                "external_network": False,
                "real_model_calls": 0,
            }
        )
    )
finally:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()
    server.shutdown()
    server.server_close()
