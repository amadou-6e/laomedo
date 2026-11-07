"""Build real maintained provider graphs using observed runtime catalogues."""

import importlib.util
import json
import sys
from pathlib import Path


def main():
    root = Path("C:/CodeWorkspace/laomedo")
    evidence = root / "claude-review.local/agents-250-20261107"
    state = Path(
        json.loads((evidence / "runtime-path.json").read_text(encoding="utf-8"))["path"]
    )
    spec = importlib.util.spec_from_file_location(
        "maintained_agents",
        root / ".tools/agent-refactor-205/examples/agents/build_flow.py",
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    chosen = {
        "codex": "gpt-6-luna",
        "claude": "haiku",
        "opencode": "opencode-go/gpt-6-luna",
    }
    result = []
    resume = "--resume" in sys.argv
    for provider, port in [("codex", 18815), ("claude", 18816), ("opencode", 18817)]:
        catalog = json.loads(
            (state / (provider + "-catalog.json")).read_text(encoding="utf-8")
        )
        models = catalog["models"]
        selected = next(m for m in models if m["id"] == chosen[provider])
        effort = "low" if "low" in selected["efforts"] else selected["efforts"][0]
        flow = module.build(
            provider=provider,
            model=selected["id"],
            effort=effort,
            runner_url=f"http://127.0.0.1:{port}",
            workflow="resume" if resume else "fresh",
            follow_up=(
                "Using the README you just read, name its first heading and one documented entry point for a developer. Do not reread or edit files, use the network, or delegate."
                if resume
                else None
            ),
            task="Read the actual README.md in your working directory. Report its first Markdown heading and summarize what this repository does in two sentences. Do not edit files, access the network, or delegate to another agent.",
        )
        flow["name"] = f"{provider.title()} Agent - PR250 " + (
            "resume" if resume else "live validation"
        )
        for node in flow["data"]["nodes"]:
            template = node["data"]["node"]["template"]
            template["model"]["options"] = [m["id"] for m in models]
            template["effort"]["options"] = selected["efforts"]
        (state / (provider + ("-resume" if resume else "") + "-flow.json")).write_text(
            json.dumps(flow), encoding="utf-8"
        )
        result.append(
            {
                "provider": provider,
                "model": selected["id"],
                "effort": effort,
                "nodes": len(flow["data"]["nodes"]),
                "edges": len(flow["data"]["edges"]),
            }
        )
    (
        evidence / (("resume" if resume else "live") + "-graph-configuration.json")
    ).write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
