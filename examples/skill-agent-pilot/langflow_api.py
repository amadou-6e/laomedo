"""Import the saved Langflow flow, then optionally trigger its run API."""

import argparse
import json
import os
from pathlib import Path
import sys
from urllib import error, request

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from laomedo.local_runner import _private


HERE = Path(__file__).resolve().parent


def call(base: str, method: str, path: str, payload: dict) -> dict:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    key = os.environ.get("LANGFLOW_API_KEY")
    if key:
        headers["x-api-key"] = key
    req = request.Request(base.rstrip("/") + path,
                          data=json.dumps(payload).encode("utf-8"),
                          headers=headers, method=method)
    try:
        with request.urlopen(req, timeout=240) as response:
            return json.load(response)
    except error.HTTPError as exc:
        details = exc.read(1024).decode("utf-8", errors="replace")
        raise RuntimeError(f"Langflow HTTP {exc.code}: {details}") from exc


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=("import", "run"))
    parser.add_argument("--base", default="http://127.0.0.1:7861")
    parser.add_argument("--flow-id")
    parser.add_argument("--task")
    parser.add_argument("--private-report", type=Path)
    args = parser.parse_args()
    if args.operation == "import":
        flow = json.loads((HERE / "pilot-flow.json").read_text(encoding="utf-8"))
        flow.pop("id", None)
        result = call(args.base, "POST", "/api/v1/flows/", flow)
        print("flow_id=" + result["id"])
        return
    if not args.flow_id or not args.task or not args.private_report:
        parser.error("run requires --flow-id, --task, and --private-report")
    report = _private(args.private_report)
    report.parent.mkdir(parents=True, exist_ok=True)
    result = call(args.base, "POST", "/api/v1/run/" + args.flow_id,
                  {"input_value": args.task, "input_type": "chat",
                   "output_type": "chat"})
    report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print("langflow_response_saved_outside_git=true")
    print("flow_id=" + args.flow_id)


if __name__ == "__main__":
    main()
