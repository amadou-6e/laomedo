"""Real native App Server + OTLP feasibility probe. Never invokes a PR agent."""

from collections import Counter
from datetime import datetime
from datetime import timezone
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer
import argparse
import hashlib
import json
import os
from pathlib import Path
import queue
import re
import secrets
import shutil
import subprocess
import tempfile
import threading
import time

from opentelemetry.proto.collector.logs.v1.logs_service_pb2 import (
    ExportLogsServiceRequest,
)
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)


def timestamp():
    return datetime.now(timezone.utc).isoformat()


def run(executable, source, summary_path):
    private = Path(tempfile.mkdtemp(prefix="laomedo-otel-feasibility-"))
    workspace = private / "workspace"
    workspace.mkdir()
    shutil.copy2(source / "README.md", workspace / "README.md")
    token = secrets.token_urlsafe(32)
    received = []

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.headers.get("Authorization") != "Bearer " + token:
                self.send_error(401)
                return
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16 * 1024 * 1024:
                self.send_error(413)
                return
            body = self.rfile.read(length)
            if self.path not in {"/v1/logs", "/v1/traces"}:
                self.send_error(404)
                return
            message = (
                ExportLogsServiceRequest()
                if self.path == "/v1/logs"
                else ExportTraceServiceRequest()
            )
            message.ParseFromString(body)
            received.append((timestamp(), self.path, message))
            (private / f"otlp-{len(received)}.pb").write_bytes(body)
            self.send_response(200)
            self.send_header("Content-Type", "application/x-protobuf")
            self.send_header("Content-Length", "0")
            self.end_headers()

    collector = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=collector.serve_forever, daemon=True).start()
    base = "http://127.0.0.1:" + str(collector.server_port)
    exporter = (
        lambda signal: '{otlp-http={endpoint="'
        + base
        + "/v1/"
        + signal
        + '",protocol="binary",headers={Authorization="Bearer '
        + token
        + '"}}}'
    )
    command = [
        executable,
        "-c",
        "otel.exporter=" + exporter("logs"),
        "-c",
        "otel.trace_exporter=" + exporter("traces"),
        "-c",
        "otel.log_user_prompt=false",
        "app-server",
    ]
    stderr = (private / "stderr.log").open("w", encoding="utf-8")
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=stderr,
        text=True,
        encoding="utf-8",
        cwd=workspace,
    )
    incoming = queue.Queue()
    records = []
    serial = 0

    def read():
        with (private / "native.jsonl").open("w", encoding="utf-8") as output:
            for line in process.stdout:
                event = {"received_at": timestamp(), "native": json.loads(line)}
                records.append(event)
                output.write(json.dumps(event) + "\n")
                output.flush()
                incoming.put(event["native"])

    reader = threading.Thread(target=read, daemon=True)
    reader.start()

    def send(method, params, request=True):
        nonlocal serial
        message = {"method": method, "params": params}
        if request:
            serial += 1
            message["id"] = serial
        process.stdin.write(json.dumps(message) + "\n")
        process.stdin.flush()
        return serial

    def next_message(deadline):
        while time.monotonic() < deadline:
            try:
                message = incoming.get(timeout=min(0.5, deadline - time.monotonic()))
            except queue.Empty:
                if process.poll() is not None:
                    raise RuntimeError("app_server_exited")
                continue
            if "method" in message and "id" in message:
                # This probe never grants an approval or executes a dynamic tool.
                process.stdin.write(
                    json.dumps(
                        {
                            "id": message["id"],
                            "error": {
                                "code": -32601,
                                "message": "probe approval/tool request refused",
                            },
                        }
                    )
                    + "\n"
                )
                process.stdin.flush()
                continue
            return message
        raise TimeoutError("native_response_deadline")

    def request(method, params):
        identity = send(method, params)
        deadline = time.monotonic() + 30
        while True:
            message = next_message(deadline)
            if message.get("id") == identity:
                if "error" in message:
                    raise RuntimeError(
                        "native_request_rejected:"
                        + method
                        + ":"
                        + str(message["error"].get("message"))
                    )
                return message.get("result", {})

    turns = []
    native_thread = None
    error = None
    started = timestamp()
    attempt_count = 0
    try:
        request(
            "initialize",
            {
                "clientInfo": {"name": "laomedo_observability_probe", "version": "0.1"},
                "capabilities": {"experimentalApi": True},
            },
        )
        send("initialized", {}, False)
        result = request(
            "thread/start",
            {
                "cwd": str(workspace),
                "approvalPolicy": "never",
                "sandbox": "read-only",
                "ephemeral": True,
            },
        )
        native_thread = result["thread"]["id"]
        prompts = [
            "Use one read-only shell command to read the first five lines of README.md, then name this project in one short sentence. Do not edit files, access network, read any other file, use MCP, or spawn subagents.",
            "Continue this same conversation. Without tools, state the project name you just read in at most five words.",
            "Use a single read-only shell command that waits 15 seconds before returning. Do not edit files, access network, read other files, or spawn subagents.",
        ]
        for index, prompt in enumerate(prompts):
            attempt_count += 1
            response = request(
                "turn/start",
                {
                    "threadId": native_thread,
                    "input": [{"type": "text", "text": prompt}],
                    "approvalPolicy": "never",
                    "sandboxPolicy": {"type": "readOnly"},
                },
            )
            turn_id = response["turn"]["id"]
            if index == 2:
                request(
                    "turn/interrupt", {"threadId": native_thread, "turnId": turn_id}
                )
            deadline = time.monotonic() + 90
            while True:
                message = next(
                    (
                        entry["native"]
                        for entry in reversed(records)
                        if entry["native"].get("method") == "turn/completed"
                        and entry["native"].get("params", {}).get("turn", {}).get("id")
                        == turn_id
                    ),
                    None,
                )
                if message is None:
                    message = next_message(deadline)
                params = message.get("params") or {}
                if (
                    message.get("method") == "turn/completed"
                    and params.get("turn", {}).get("id") == turn_id
                ):
                    turns.append({"id": turn_id, "status": params["turn"]["status"]})
                    break
        history = request(
            "thread/read", {"threadId": native_thread, "includeTurns": True}
        )
        (private / "history.json").write_text(json.dumps(history), encoding="utf-8")
    except Exception as exc:
        error = type(exc).__name__ + ":" + str(exc)
    finally:
        process.stdin.close()
        try:
            process.wait(timeout=15)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
        reader.join(timeout=5)
        stderr.close()
        collector.shutdown()
        collector.server_close()
    methods = Counter(entry["native"].get("method", "response") for entry in records)
    items = [
        entry["native"].get("params", {}).get("item", {})
        for entry in records
        if entry["native"].get("method") == "item/completed"
    ]
    usage = [
        entry["native"].get("params", {})
        for entry in records
        if entry["native"].get("method") == "thread/tokenUsage/updated"
    ]
    otel_names = Counter()
    attribute_keys = set()
    correlated = False
    cost_keys = set()
    spans = Counter()
    for _, path, message in received:
        if path == "/v1/logs":
            for resource in message.resource_logs:
                for scope in resource.scope_logs:
                    for record in scope.log_records:
                        attributes = {
                            item.key: item.value for item in record.attributes
                        }
                        attribute_keys.update(attributes)
                        candidate = record.event_name or record.body.string_value
                        name = (
                            candidate
                            if re.fullmatch(r"codex\.[a-zA-Z0-9_.]+", candidate)
                            else "unnamed"
                        )
                        otel_names[name] += 1
                        for key, value in attributes.items():
                            if value.string_value == native_thread:
                                correlated = True
                            if "cost" in key.lower():
                                cost_keys.add(key)
        else:
            for resource in message.resource_spans:
                for scope in resource.scope_spans:
                    for span in scope.spans:
                        name = (
                            span.name
                            if re.fullmatch(r"codex[.a-zA-Z0-9_]+", span.name)
                            else "unnamed"
                        )
                        spans[name] += 1
    summary = {
        "date": "2026-10-15",
        "scope": "real host App Server and OTLP; original Docker runner blocked",
        "cli_version": subprocess.check_output(
            [executable, "--version"], text=True
        ).strip(),
        "original_runner_cli": "codex-cli 0.159.2",
        "docker_engine": "unavailable",
        "started": started,
        "ended": timestamp(),
        "top_level_turns_attempted": attempt_count,
        "turns": turns,
        "native_method_counts": dict(methods),
        "completed_item_types": dict(
            Counter(item.get("type", "unknown") for item in items)
        ),
        "native_token_usage_updates": len(usage),
        "usage_counter_keys": sorted(
            {key for item in usage for key in (item.get("tokenUsage") or {})}
        ),
        "otlp_batches": len(received),
        "otel_event_names": dict(otel_names),
        "otel_attribute_keys": sorted(attribute_keys),
        "otel_span_names": dict(spans),
        "otel_thread_correlation_observed": correlated,
        "observed_cost_attribute_names": sorted(cost_keys),
        "subagent_execution": "not exercised",
        "graph_run_correlation": "not exercised",
        "parallel_agent_capture": "not exercised",
        "original_agent_acceptance": False,
        "cost": "unknown; no invoice or price estimate inferred",
        "error": error,
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "protocol_sha256": hashlib.sha256(
            Path(__file__).with_name("PROTOCOL.md").read_bytes()
        ).hexdigest(),
    }
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "summary": str(summary_path),
                "private_evidence": str(private),
                "turns": len(turns),
                "error": error,
            }
        )
    )
    return 0 if error is None else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--executable", required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.executable, args.source, args.summary))
