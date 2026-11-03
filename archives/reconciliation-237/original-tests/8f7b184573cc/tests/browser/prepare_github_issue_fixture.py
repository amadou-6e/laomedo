"""Import actual nodes into a disposable fake-provider Langflow viewer only."""

import urllib.request
import json
import gzip
import time
import copy
import uuid
from pathlib import Path
import argparse

parser = argparse.ArgumentParser()
parser.add_argument("--manifest", required=True)
parser.add_argument("--base", default="http://127.0.0.1:7866")
parser.add_argument("--action", choices=["read", "modify", "close"], default="read")
args = parser.parse_args()
root = Path(__file__).resolve().parents[2]
base = args.base.rstrip("/")
from urllib.parse import urlparse

parsed = urlparse(base)
if (
    parsed.scheme != "http"
    or parsed.hostname != "127.0.0.1"
    or parsed.path
    or parsed.query
    or parsed.fragment
):
    raise ValueError("disposable loopback viewer required")
p = Path(args.manifest)
f = json.loads(p.read_text(encoding="utf-8"))
if f.get("provider") != "fake-no-network":
    raise ValueError("fake fixture required")
for attempt in range(35):
    try:
        token = json.load(
            urllib.request.urlopen(base + "/api/v1/auto_login", timeout=5)
        )["access_token"]
        break
    except Exception:
        if attempt == 34:
            raise
        time.sleep(1)


def request(path, body):
    response = urllib.request.urlopen(
        urllib.request.Request(
            base + path,
            data=json.dumps(body).encode(),
            headers={
                "Authorization": "Bearer " + token,
                "Content-Type": "application/json",
            },
        ),
        timeout=90,
    )
    raw = response.read()
    return json.loads(
        gzip.decompress(raw)
        if response.headers.get("Content-Encoding") == "gzip"
        else raw
    )


code = (root / "components/laomedo/github_issue.py").read_text(encoding="utf-8")
definition = request("/api/v1/custom_component", {"code": code})["data"]
definition = request(
    "/api/v1/custom_component/update",
    {
        "code": code,
        "template": definition["template"],
        "field": "repository_url",
        "field_value": "https://github.com/owner/repo",
    },
)
assert definition["template"]["labels"]["options"] == ["backend", "research"]
definition["template"]["issue_choice"]["value"] = next(
    choice
    for choice in definition["template"]["issue_choice"]["options"]
    if choice.startswith("#1 ")
)

reader = copy.deepcopy(definition)
reader["template"]["state"]["value"] = "all"
writer = copy.deepcopy(definition)
writer["template"]["state"]["value"] = "all"
writer["template"]["issue_choice"]["value"] = ""
case = uuid.uuid4().hex[:8]
op_code = """from lfx.custom.custom_component.component import Component
from lfx.io import Output
from lfx.schema import Data
class FixtureIssueOperation(Component):
    display_name='Fixture operation'
    name='FixtureIssueOperation'
    inputs=[]
    outputs=[Output(name='operation',display_name='Operation',method='operation_output')]
    def operation_output(self)->Data:
        return Data(data={'action':'modify','request_id':'browser-modify-CASE','grant_ref':'fixture','changes':{'title':'Updated through graph','body':'Changed through incoming graph node CASE','labels':['research']}})
"""
op_code = op_code.replace("CASE", case)
if args.action == "close":
    op_code = op_code.replace("'action':'modify'", "'action':'close'").replace(
        ",'changes':{'title':'Updated through graph','body':'Changed through incoming graph node "
        + case
        + "','labels':['research']}",
        "",
    )
operation = request("/api/v1/custom_component", {"code": op_code})["data"]


def node(identity, kind, definition, x, y):
    return {
        "id": identity,
        "type": "genericNode",
        "position": {"x": x, "y": y},
        "data": {"id": identity, "type": kind, "node": definition},
    }


def edge(source, source_kind, output, target, field):
    sh = {
        "dataType": source_kind,
        "id": source,
        "name": output,
        "output_types": ["JSON"],
    }
    th = {
        "fieldName": field,
        "id": target,
        "inputTypes": ["Data", "JSON"],
        "type": "other",
    }
    return {
        "id": source + "-" + field,
        "source": source,
        "target": target,
        "sourceHandle": json.dumps(sh),
        "targetHandle": json.dumps(th),
        "data": {"sourceHandle": sh, "targetHandle": th},
    }


nodes = [
    node("issue", "LaomedoGitHubIssue", reader, 30, 40),
    node("operation", "FixtureIssueOperation", operation, 30, 580),
    node("apply", "LaomedoGitHubIssue", writer, 570, 160),
]
edges = [
    edge("issue", "LaomedoGitHubIssue", "issue", "apply", "issue_reference"),
    edge("operation", "FixtureIssueOperation", "operation", "apply", "operation"),
]
if args.action == "read":
    nodes = [node("issue", "LaomedoGitHubIssue", definition, 50, 50)]
    edges = []
flow = request(
    "/api/v1/flows/",
    {
        "name": "Credential-free live GitHub Issue operations",
        "description": "Fake GitHub and an incoming operation; no agents or publisher.",
        "data": {
            "nodes": nodes,
            "edges": edges,
            "viewport": {"x": 20, "y": 20, "zoom": 0.8},
        },
    },
)
if args.action == "read":
    f.update(flow_id=flow["id"], url=base + "/flow/" + flow["id"])
else:
    f.update(
        operation_flow_id=flow["id"],
        operation_url=base + "/flow/" + flow["id"],
        operation_action=args.action,
    )
p.write_text(json.dumps(f, indent=2), encoding="utf-8")
print(
    json.dumps(
        {
            "imported_operations_flow": flow["id"],
            "edges": len(edges),
            "provider": "fake",
        }
    )
)
