"""Check native quota availability with the exact SIWC provider config, without credentials/network."""

import json
import subprocess
import queue
import threading

image = "laomedo-codex-acp:0.159.2-2.1.1-quota1"
config = [
    'model_provider="openai_chatgpt_plan"',
    'model_providers.openai_chatgpt_plan.name="ChatGPT plan"',
    'model_providers.openai_chatgpt_plan.base_url="https://api.openai.com/v1"',
    'model_providers.openai_chatgpt_plan.env_key="ACCESS_TOKEN"',
    'model_providers.openai_chatgpt_plan.wire_api="responses"',
    "model_providers.openai_chatgpt_plan.requires_openai_auth=false",
    "model_providers.openai_chatgpt_plan.supports_websockets=false",
]
command = [
    "docker",
    "run",
    "--rm",
    "-i",
    "--network",
    "none",
    "--read-only",
    "--tmpfs",
    "/tmp:rw,noexec,nosuid,size=64m",
    "-e",
    "CODEX_HOME=/tmp",
    image,
    "codex",
    "app-server",
    "--listen",
    "stdio://",
]
for value in config:
    command.extend(["-c", value])
messages = [
    {
        "id": 0,
        "method": "initialize",
        "params": {
            "clientInfo": {"name": "laomedo_quota_contract_check", "version": "0"}
        },
    },
    {"method": "initialized", "params": {}},
    {"id": 1, "method": "account/rateLimits/read", "params": {}},
]
process = subprocess.Popen(
    command,
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.DEVNULL,
    text=True,
)
replies = queue.Queue()


def read_stdout():
    for line in process.stdout:
        try:
            replies.put(json.loads(line))
        except ValueError:
            continue


threading.Thread(target=read_stdout, daemon=True).start()
try:
    process.stdin.write(json.dumps(messages[0]) + "\n")
    process.stdin.flush()
    while replies.get(timeout=30).get("id") != 0:
        pass
    for message in messages[1:]:
        process.stdin.write(json.dumps(message) + "\n")
    process.stdin.flush()
    while True:
        message = replies.get(timeout=30)
        if message.get("id") == 1:
            print(
                json.dumps(
                    {
                        "quota_reply": message,
                        "network": "none",
                        "credentials": "none",
                        "submitted_turns": 0,
                    }
                )
            )
            break
finally:
    process.stdin.close()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.terminate()
        process.wait(timeout=10)
