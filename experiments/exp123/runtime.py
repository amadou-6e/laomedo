"""Synthetic ingress and single-graph worker for the frozen EXP-123 candidate."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import threading
import time
from urllib import parse, request
from uuid import NAMESPACE_URL, uuid5

BASE = "http://127.0.0.1:18743"
FIXTURE_KEY = b"exp123-synthetic-fixture-key"
HEADS = ("1" * 40, "2" * 40)
HERE = Path(__file__).resolve().parent


def signed(payload: dict) -> dict:
    value = {k: v for k, v in payload.items() if k != "signature"}
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return {**value, "signature": hmac.new(FIXTURE_KEY, raw, hashlib.sha256).hexdigest()}


def call(method: str, path: str, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = request.Request(BASE + path, data=data, method=method,
                          headers={"Content-Type": "application/json"})
    with request.urlopen(req, timeout=1) as response:
        return json.load(response)


def node_event(case_ref, kind, node, graph, **fields):
    return call("POST", "/node", {**fields, "run_id": case_ref,
        "kind": kind, "node_id": node, "graph_id": graph})


def fetch_observation(run, gate, head):
    return call("GET", "/observation?" + parse.urlencode(
        {"run_id": run, "gate_id": gate, "head_sha": head}))


class FixtureStore:
    def __init__(self, path: Path):
        self.path = path
        self.lock = threading.RLock()
        self.rows = []
        self.cases = {}
        self.deliveries = {}
        self.checks = {}
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                self._apply(json.loads(line))
        for run, case in list(self.cases.items()):
            if case["state"] == "running":
                self.append("case_terminal", run, state="crashed", reason="worker_restart")

    def _apply(self, row):
        self.rows.append(row)
        run = row["run_id"]
        if row["kind"] == "case_reserved":
            self.cases[run] = {"state": "running", "name": row["case_name"]}
        elif row["kind"] == "case_terminal":
            self.cases[run]["state"] = row["state"]
        elif row["kind"] == "delivery":
            fixture = row["fixture"]
            if row["classification"] == "accepted":
                self.deliveries[(run, fixture["source_delivery_id"])] = fixture
                key = (run, fixture["gate_id"], fixture["head_sha"], fixture["source_check_id"])
                self.checks[key] = fixture

    def append(self, kind, run, **fields):
        with self.lock:
            row = {**fields, "kind": kind, "run_id": run,
                   "sequence": len(self.rows) + 1, "monotonic": time.monotonic(),
                   "utc": datetime.now(timezone.utc).isoformat()}
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(row, sort_keys=True) + "\n")
                stream.flush()
                os.fsync(stream.fileno())
            self._apply(row)
            return row

    def reserve(self, run, name):
        if not re.fullmatch(r"exp123-S1-[a-z_-]{1,30}", run):
            raise ValueError("run_identity_invalid")
        with self.lock:
            if run in self.cases:
                raise ValueError("case_identity_consumed")
            self.append("case_reserved", run, case_name=name)

    def observe(self, fixture):
        run = fixture.get("run_id", "invalid")
        with self.lock:
            classification = "refused"
            required = {"run_id", "gate_id", "repository", "pr_number", "head_sha",
                        "source_check_id", "source_delivery_id", "status", "signature"}
            valid = (set(fixture) == required and run in self.cases and
                     fixture["repository"] == "fixture/repo" and fixture["pr_number"] == 1 and
                     fixture["head_sha"] in HEADS and fixture["status"] in
                     {"pending", "unknown", "passed", "failed"} and
                     isinstance(fixture["source_delivery_id"], str) and
                     hmac.compare_digest(str(fixture["signature"]), signed(fixture)["signature"]))
            if valid:
                index = HEADS.index(fixture["head_sha"]) + 1
                valid = (fixture["gate_id"] == run + ":gate-" + str(index) and
                         fixture["source_check_id"] == run + ":check-" + str(index))
            if valid and self.cases[run]["state"] != "running":
                classification = "inactive"
            elif valid:
                prior_delivery = self.deliveries.get((run, fixture["source_delivery_id"]))
                key = (run, fixture["gate_id"], fixture["head_sha"], fixture["source_check_id"])
                prior = self.checks.get(key)
                if prior_delivery:
                    classification = "duplicate" if prior_delivery == fixture else "conflict"
                elif prior and prior["status"] in {"passed", "failed"}:
                    classification = "duplicate" if fixture["status"] == prior["status"] else "conflict"
                else:
                    classification = "accepted"
            self.append("delivery", run, classification=classification, fixture=fixture)
            return {"classification": classification}

    def observation(self, run, gate, head):
        with self.lock:
            if run not in self.cases or self.cases[run]["state"] != "running":
                return {"status": "unknown"}
            rows = [value for (r, g, h, _), value in self.checks.items()
                    if (r, g, h) == (run, gate, head)]
            if len(rows) != 1:
                return {"status": "unknown"}
            return {"status": rows[0]["status"], "source_check_id": rows[0]["source_check_id"]}

    def snapshot(self, run):
        with self.lock:
            return {"run_id": run, "state": self.cases.get(run, {}).get("state", "absent"),
                    "events": [row for row in self.rows if row["run_id"] == run]}


def graph_payload(run):
    from lfx.custom.custom_component.component import Component
    from lfx.custom.utils import build_custom_component_template
    def node(stem, node_id, values):
        code = (HERE / (stem + ".py")).read_text(encoding="utf-8")
        template, _ = build_custom_component_template(Component(_code=code))
        for field, value in values.items():
            template["template"][field]["value"] = value
        return {"id": node_id, "type": "genericNode", "position": {"x": 0, "y": 0},
                "data": {"id": node_id, "type": "Exp123" + stem.title(), "node": template}}
    def edge(source, output_name, target, input_name):
        output = next(item for item in source["data"]["node"]["outputs"]
                      if item["name"] == output_name)
        field = target["data"]["node"]["template"][input_name]
        outgoing = {"dataType": source["data"]["type"], "id": source["id"],
                    "name": output_name, "output_types": output["types"]}
        incoming = {"id": target["id"], "fieldName": input_name,
                    "inputTypes": field.get("input_types", []), "type": field["type"]}
        return {"id": source["id"] + output_name + target["id"],
                "source": source["id"], "target": target["id"],
                "sourceHandle": json.dumps(outgoing), "targetHandle": json.dumps(incoming),
                "data": {"sourceHandle": outgoing, "targetHandle": incoming}}
    a1 = node("agent", "Agent1", {"context": json.dumps({"run_id": run}), "iteration": 1})
    a2 = node("agent", "Agent2", {"iteration": 2})
    g1, g2 = node("gate", "Gate1", {}), node("gate", "Gate2", {})
    router = node("router", "Router", {})
    t1, t2 = node("terminal", "Result1", {}), node("terminal", "Result2", {})
    return {"id": str(uuid5(NAMESPACE_URL, run)), "name": "EXP-123", "data": {"nodes": [a1, g1, router, t1, a2, g2, t2],
        "edges": [edge(a1, "delivery", g1, "delivery"), edge(g1, "result", router, "check"),
                  edge(router, "success", t1, "check"), edge(router, "failure", a2, "context"),
                  edge(a2, "delivery", g2, "delivery"), edge(g2, "result", t2, "check")]}}


async def serve(state):
    from importlib.metadata import version
    from lfx.graph.graph.base import Graph
    if version("langflow") != "1.12.3" or version("lfx") != "1.12.3":
        raise RuntimeError("pinned_runtime_unavailable")
    store = FixtureStore(state / "journal.jsonl")
    loop = asyncio.get_running_loop()
    tasks = {}
    async def execute(run):
        try:
            payload = graph_payload(run)
            graph = Graph.from_payload(payload)
            graph.set_run_id()
            snapshot = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
            with (state / (run + ".flow.json")).open("xb") as frozen:
                frozen.write(snapshot + b"\n")
                frozen.flush()
                os.fsync(frozen.fileno())
            store.append("graph_started", run, graph_id=str(graph.run_id),
                         graph_sha256=hashlib.sha256(snapshot + b"\n").hexdigest())
            await graph.arun(inputs=[{}], types=[None], outputs=["Result1", "Result2"])
            store.append("case_terminal", run, state="completed")
        except asyncio.CancelledError:
            store.append("case_terminal", run, state="interrupted")
            raise
        except Exception as failure:
            store.append("case_terminal", run, state="failed", error_class=type(failure).__name__,
                         error=str(failure)[:600])
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def reply(self, code, payload):
            raw = json.dumps(payload).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def do_GET(self):
            parsed = parse.urlsplit(self.path)
            fields = {k: v[0] for k, v in parse.parse_qs(parsed.query).items()}
            if parsed.path == "/health":
                self.reply(200, {"ready": True})
            elif parsed.path == "/case":
                self.reply(200, store.snapshot(fields["run_id"]))
            elif parsed.path == "/observation":
                self.reply(200, store.observation(fields["run_id"], fields["gate_id"], fields["head_sha"]))
            else:
                self.reply(404, {})
        def do_POST(self):
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 16384:
                    raise ValueError("request_size")
                payload = json.loads(self.rfile.read(length))
                run = payload.get("run_id", "invalid")
                if self.path == "/reserve":
                    store.reserve(run, payload["case_name"])
                    self.reply(200, {"reserved": True})
                elif self.path == "/start":
                    with store.lock:
                        if run not in store.cases or store.cases[run]["state"] != "running" or run in tasks:
                            raise ValueError("case_not_dispatchable")
                        if any(row["kind"] == "graph_started" for row in store.snapshot(run)["events"]):
                            raise ValueError("case_already_dispatched")
                        tasks[run] = asyncio.run_coroutine_threadsafe(execute(run), loop)
                    self.reply(202, {"started": True})
                elif self.path == "/event":
                    self.reply(200, store.observe(payload))
                elif self.path == "/node":
                    kind = payload.pop("kind")
                    payload.pop("run_id")
                    store.append(kind, run, **payload)
                    self.reply(200, {"saved": True})
                elif self.path == "/stop":
                    store.append("stop_requested", run)
                    active = tasks.get(run)
                    self.reply(200, {"cancel_requested": active.cancel() if active else False})
                else:
                    self.reply(404, {})
            except (ValueError, KeyError, TypeError):
                self.reply(409, {"error": "fixture_request_invalid"})
    server = ThreadingHTTPServer(("0.0.0.0", 18743), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        await asyncio.Event().wait()
    finally:
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    asyncio.run(serve(Path("/state")))
