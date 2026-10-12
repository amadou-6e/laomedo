"""Explicit offline migration of known two-port contract exports. Never overwrites input."""
from copy import deepcopy
import argparse
import json
from pathlib import Path
from lfx.custom.custom_component.component import Component
from lfx.custom.utils import build_custom_component_template

ROOT = Path(__file__).resolve().parents[2]


def migrate(flow):
    result = deepcopy(flow)
    code = (ROOT / "components/laomedo/output_contract_legacy.py").read_text(encoding="utf-8")
    original = code.replace("LaomedoOutputContractLegacy", "LaomedoOutputContract").replace("Laomedo Output Contract (legacy)", "Laomedo Output Contract")
    changed = set()
    for node in result["data"]["nodes"]:
        if node["data"]["type"] != "LaomedoOutputContract":
            continue
        old = node["data"]["node"]
        ports = [port["name"] for port in old["outputs"]]
        if ports == ["success", "failure", "rejection", "recovery"]:
            continue
        if ports != ["requirements", "validation"] or old["template"]["code"]["value"].strip() != original.strip():
            raise ValueError("unsupported_legacy_contract_source")
        template, _ = build_custom_component_template(Component(_code=code))
        for name, field in old["template"].items():
            if name != "code" and name in template["template"] and "value" in field:
                template["template"][name]["value"] = deepcopy(field["value"])
        node["data"]["type"] = "LaomedoOutputContractLegacy"
        node["data"]["node"] = template
        changed.add(node["id"])
    for edge in result["data"]["edges"]:
        if edge["source"] in changed:
            edge["data"]["sourceHandle"]["dataType"] = "LaomedoOutputContractLegacy"
            edge["sourceHandle"] = edge["sourceHandle"].replace("LaomedoOutputContract", "LaomedoOutputContractLegacy")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    updated = migrate(json.loads(args.input.read_text(encoding="utf-8")))
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(updated, indent=2) + "\n")
