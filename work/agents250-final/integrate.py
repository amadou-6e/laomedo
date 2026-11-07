"""Explicit three-way integration of already accepted feature owners."""

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path("C:/CodeWorkspace/laomedo/.tools/agent-refactor-205")
EVIDENCE = Path("C:/CodeWorkspace/laomedo/claude-review.local/agents-250-20261107")
MISSING = object()


def stage(number, path):
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "show", f":{number}:{path}"]
    )


def write(path, text):
    (ROOT / path).write_text(text, encoding="utf-8")


def choose(path, choices):
    text = (ROOT / path).read_text(encoding="utf-8")
    pattern = r"^<<<<<<<[^\n]*\n(.*?)^=======\n(.*?)^>>>>>>>[^\n]*\n"
    index = 0

    def replace(match):
        nonlocal index
        choice = choices[index]
        index += 1
        return match.group(choice) if isinstance(choice, int) else choice

    text = re.sub(pattern, replace, text, flags=re.M | re.S)
    assert index == len(choices), (path, index, len(choices))
    write(path, text)


def merge(base, ours, theirs, location, conflicts):
    if ours == theirs or theirs == base:
        return ours
    if ours == base:
        return theirs
    if all(isinstance(v, dict) for v in (base, ours, theirs)):
        result = {}
        for key in dict.fromkeys([*base, *ours, *theirs]):
            value = merge(
                base.get(key, MISSING),
                ours.get(key, MISSING),
                theirs.get(key, MISSING),
                location + "/" + key,
                conflicts,
            )
            if value is not MISSING:
                result[key] = value
        return result
    if all(isinstance(v, list) for v in (base, ours, theirs)) and all(
        isinstance(v, dict) and "id" in v for seq in (base, ours, theirs) for v in seq
    ):
        maps = [{v["id"]: v for v in seq} for seq in (base, ours, theirs)]
        assert all(
            len(seq) == len(mapping) for seq, mapping in zip((base, ours, theirs), maps)
        )
        result = merge(*maps, location, conflicts)
        return list(result.values())
    conflicts.append(
        {"path": location, "ours": str(ours)[:250], "theirs": str(theirs)[:250]}
    )
    return ours


def main():
    paths = subprocess.check_output(
        ["git", "-C", str(ROOT), "diff", "--name-only", "--diff-filter=U"], text=True
    ).splitlines()
    ledger = []
    for path in paths:
        hashes = {}
        for number in (1, 2, 3):
            result = subprocess.run(
                ["git", "-C", str(ROOT), "show", f":{number}:{path}"],
                capture_output=True,
            )
            if result.returncode == 0:
                hashes[str(number)] = hashlib.sha256(result.stdout).hexdigest()
        ledger.append({"path": path, "stage_sha256": hashes})
    (EVIDENCE / "integration-inputs.json").write_text(
        json.dumps(ledger, indent=2), encoding="utf-8"
    )
    for path in paths:
        if not path.endswith(".json") or path == "examples/github-pr/flow.json":
            continue
        try:
            values = [json.loads(stage(n, path)) for n in (1, 2, 3)]
        except subprocess.CalledProcessError:
            continue
        conflicts = []
        result = merge(*values, path, conflicts)
        if conflicts:
            (EVIDENCE / (path.replace("/", "--") + "-conflicts.json")).write_text(
                json.dumps(conflicts, indent=2), encoding="utf-8"
            )
            (EVIDENCE / (path.replace("/", "--") + "-candidate.json")).write_text(
                json.dumps(result, indent=2), encoding="utf-8"
            )
            print(
                path,
                "unresolved values",
                len(conflicts),
                [v["path"] for v in conflicts],
            )
        else:
            write(path, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
            print(path, "merged keys without conflicting values")
    if "--json-only" in sys.argv:
        return
    choose(".gitattributes", [1])
    p = ".gitattributes"
    write(
        p,
        (ROOT / p)
        .read_text(encoding="utf-8")
        .replace(
            "frontend/langflow-skill-viewer/upstream.patch ",
            "frontend/langflow-skill-viewer/integration/upstream.patch ",
        ),
    )
    choose("AGENTS.md", [1])
    choose("CONTRIBUTING.md", [1])
    choose("tests/README.md", [1])
    choose(
        "frontend/langflow-skill-viewer/README.md",
        [
            "- [Skills](skills/README.md)\n- [GitHub viewers](github/README.md)\n- [Agent activity](agents/activity/README.md)\n- [Agent controls](agents/controls/README.md)\n- [Upstream integration patches](integration/README.md)\n"
            + stage(3, "frontend/langflow-skill-viewer/README.md")
            .decode("utf-8")
            .split("## Skill workspace controls", 1)[1]
            .split("## Agent activity appearance", 1)[0]
            .join(["\n## Skill workspace controls", ""])
        ],
    )
    choose(
        "src/laomedo/integrations/langflow/viewer.py",
        [
            "    from laomedo.integrations.langflow.skill_editing import install_skill_editing_routes\n\n    install_skill_editing_routes(app, authenticate)\n    from laomedo.agents.activity.routes import install_activity_routes\n\n    install_activity_routes(app, authenticate)\n    from laomedo.host.runner.routes import install_runner_service_routes\n\n"
        ],
    )
    choose("tests/support/retained.py", [1])
    choose("tests/test_github/test_interface/test_reviewed_cli.py", [1, 2])
    choose(
        "tests/test_github/test_pull_requests/test_graph/test_feedback.py",
        [
            "from laomedo.integrations.langflow.feedback.pr import operation_value\nfrom test_github.test_pull_requests.provider import FakeGitHub\n"
        ],
    )
    choose(
        "tests/test_shared/test_architecture/test_settings.py",
        [
            '            "github/interface/issues/cli.py": "os.environ.get(args.github_token_env)",\n            "github/interface/pull_requests/cli.py": "os.environ.get(args.github_token_env)",\n            "agents/interface/bridge.py": \'"LAOMEDO_" + provider.upper()\',\n'
        ],
    )
    write(
        "frontend/langflow-skill-viewer/integration/agents.patch",
        stage(2, "frontend/langflow-skill-viewer/integration/agents.patch").decode(
            "utf-8"
        ),
    )
    path = "tools/apply_langflow_skill_viewer.py"
    incoming = stage(3, path).decode("utf-8")
    own = stage(2, path).decode("utf-8")
    for name in ["claude-models.patch", "claude-selection.patch", "agents.patch"]:
        incoming = incoming.replace(
            'overlay / "' + name + '"', 'overlay / "integration/' + name + '"'
        )
    for name in [
        "AgentModelSelection.test.ts",
        "RenderAgentInputParameters.tsx",
        "AgentAdvancedControls.tsx",
        "AgentAdvancedControls.test.tsx",
    ]:
        incoming = incoming.replace(
            'overlay / "' + name + '"', 'overlay / "agents/controls/' + name + '"'
        )
    left, right = "    activity_target = ", "    recovery_target = "
    incoming = (
        incoming[: incoming.index(left)]
        + own[own.index(left) : own.index(right)]
        + incoming[incoming.index(right) :]
    )
    write(path, incoming)
    write(
        "examples/README.md",
        """# Maintained examples

Use the smallest entrypoint for the supported concern:

- [Skills](skills/README.md): source discovery, pinned inspection and versioned operations.
- [GitHub](github/README.md): selected Issue/PR inspection and PR feedback through a real Agent.
- [Agents](agents/README.md): fresh/resume graphs for each provider and explicit provenance handoffs where supported.

`graph.py` constructs native node metadata and connections without dispatching work.
Exporting or validating a graph does not establish real provider execution.
Use real references and the prerequisites in each guide; no login material belongs
in an exported graph. Historical campaigns and executed exports are preserved on
`exp` with exact revisions and hashes, rather than additional setup entrypoints.
Saved compatibility inputs belong to concern-owned tests. Remaining Shared/GitHub
campaign consumers retain their separately documented migration boundaries.
""",
    )


if __name__ == "__main__":
    main()
