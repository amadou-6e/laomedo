"""Execute one already-frozen imported graph; print only bounded outcome fields."""
import asyncio
import json
from pathlib import Path
import sys
from lfx.graph.graph.base import Graph


def outcomes(results):
    found = []
    def walk(value):
        if hasattr(value, "model_dump"):
            value = value.model_dump()
        if isinstance(value, dict):
            if "publication_state" in value and "phase" in value:
                found.append({key: value[key] for key in ("run_id", "phase", "publication_state") if key in value})
            elif "destination" in value and "issue_snapshot" in value:
                validation = value.get("routed", {}).get("validation", {})
                found.append({"destination": value["destination"],
                              "contract_status": validation.get("contract_status")})
            else:
                for item in value.values():
                    walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)
    walk(results)
    unique = {json.dumps(value, sort_keys=True): value for value in found}
    return list(unique.values())


async def run(path):
    flow = json.loads(Path(path).read_bytes())
    result = await Graph.from_payload(flow).arun(inputs=[{}],
        outputs=["publisher", "failure", "rejection", "recovery"])
    return outcomes(result)


if __name__ == "__main__":
    try:
        print(json.dumps({"outcomes": asyncio.run(run(sys.argv[1]))}, sort_keys=True))
    except Exception as failure:
        print(json.dumps({"status": "graph_failed", "error_class": type(failure).__name__}))
        raise SystemExit(1)
