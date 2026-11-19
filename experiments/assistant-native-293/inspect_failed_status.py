"""Read the owned failed chat and discover models without dispatching work."""

import json
import os
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError


if __name__ == "__main__":
    root = Path("C:/CodeWorkspace/laomedo")
    base = json.loads((root / ".tools/assistant-291-live.json").read_text(encoding="utf-8"))["base"]
    with urlopen(base + "/api/v1/auto_login", timeout=30) as response:
        token = json.load(response)["access_token"]
    for path in ("/conversations/" + os.environ["LAOMEDO_ACCEPTANCE_CONVERSATION"], "/models"):
        request = Request(base + "/api/v1/laomedo/assistant" + path, headers={"Authorization": "Bearer " + token})
        try:
            with urlopen(request, timeout=180) as response:
                data = json.load(response)
        except HTTPError as error:
            data = json.loads(error.read())
        if "conversation" in data:
            wanted = ("id", "provider", "state", "error_code", "run_id", "thread_id", "native_attempt_id", "attempt_id", "runner_instance_id", "native_action_id")
            data = {"conversation": {key: data["conversation"].get(key) for key in wanted}, "messages": [{key: item.get(key) for key in wanted} for item in data.get("messages", [])]}
        print(json.dumps(data), flush=True)
