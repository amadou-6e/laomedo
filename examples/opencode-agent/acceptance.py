"""Bounded private OpenCode Docker acceptance; stdout contains sanitized metadata only."""

import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from laomedo.local_runner import _json, _private
from laomedo.opencode_boundary import IsolatedOpenCode
from laomedo.opencode_runner import OpenCodeRunner
from laomedo.opencode_auth import console_provider
from laomedo.skill_store import SkillStore, ConflictError, inventory, tree_hash

IMAGE = "laomedo-opencode-controller:1.18.33"
IMAGE_ID = "sha256:73313fbaf91940471244ff0efb2442a333de119389875765a63bc168fec181fd"
STATE = _private(Path(os.environ["LOCALAPPDATA"]) / "Laomedo" / "opencode-27")


def profile():
    return STATE / "profile"


def secure(path):
    if os.name == "nt":
        user = subprocess.run(["whoami"], capture_output=True, text=True, check=True).stdout.strip()
        subprocess.run(["icacls", str(path), "/inheritance:r", "/grant:r", user + ":(OI)(CI)F"],
                       check=True, capture_output=True)


def setup():
    STATE.mkdir(parents=True, exist_ok=True)
    secure(STATE)
    profile().mkdir(exist_ok=True)
    if not (profile() / "auth.json").exists():
        _json(profile() / "auth.json", {"opencode-go": {"type": "api", "key": "CANARY-" + secrets.token_hex(24)}})
    source = STATE / "fixture-source"
    source.mkdir(exist_ok=True)
    (source / "fixture.txt").write_text("color: amber\ncount: 3\n", encoding="utf-8")
    for name in ("canonical", "store"):
        (STATE / name).mkdir(exist_ok=True)
        (STATE / name / "sentinel.txt").write_text("PROTECTED", encoding="utf-8")
    skill = source / ".agents/skills/laomedo-pilot"
    skill.mkdir(parents=True, exist_ok=True)
    (skill / "SKILL.md").write_text((ROOT / "examples/skill-agent-pilot/skill/SKILL.md").read_text(), encoding="utf-8")
    backend = IsolatedOpenCode(source, STATE, profile=profile(), image=IMAGE, image_id=IMAGE_ID)
    try:
        config = backend.call("GET", "/config")
        mcp = backend.call("GET", "/mcp")
        assert config["permission"]["*"] == "deny"
        assert config["tools"]["*"] is False
        assert config["tools"]["skill"] is True
        assert config["tools"]["laomedo_exec"] is True
        assert mcp["laomedo"]["status"] == "connected", mcp
        canary = json.loads((profile() / "auth.json").read_text())["opencode-go"]["key"]
        probes = {}
        for label, command in {
            "workspace": "printf BOUNDARY-OK > /draft/canary.txt && cat /draft/canary.txt",
            "auth_file": "cat /controller-auth.json /home/runner/.local/share/opencode/auth.json",
            "controller_proc": "cat /proc/1/environ",
            "canonical_write": "printf FORBIDDEN > /canonical/sentinel.txt",
            "store_write": "printf FORBIDDEN > /store/sentinel.txt",
        }.items():
            result = backend.broker.execute(command)
            assert canary not in result["stdout"] + result["stderr"]
            probes[label] = result["exit_code"]
        assert probes["workspace"] == 0
        assert probes["auth_file"] != 0
        assert probes["canonical_write"] != 0 and probes["store_write"] != 0
        assert (STATE / "canonical/sentinel.txt").read_text() == "PROTECTED"
        assert (STATE / "store/sentinel.txt").read_text() == "PROTECTED"
        result = {"status": "boundary_preflight_passed", "image": IMAGE, "image_id": IMAGE_ID,
                  "native_mcp_connected": True, "configured_tool_allowlist_verified": True,
                  "canary_absent_from_worker_outputs": True, "probe_exit_codes": probes,
                  "submitted_turns": 0}
        _json(STATE / "boundary-evidence.json", result)
        print(json.dumps(result))
    finally:
        backend.close()


def auth():
    assert json.loads((STATE / "boundary-evidence.json").read_text())["status"] == "boundary_preflight_passed"
    # Capture resolved config in memory only. Copy exactly one provider key, never
    # the personal config/plugin/skill/session trees or API URLs/settings.
    selected, organization, routing = console_provider(
        Path(os.environ["USERPROFILE"]) / ".local/share/opencode/opencode.db", include_routing=True)
    _json(profile() / "auth.json", {"opencode-go": selected})
    _json(profile() / "provider-options.json", {"provider": {"opencode-go": {
        **routing,
        "options": {"headers": {"x-opencode-org-id": organization}}}}})
    _json(STATE / "auth-handoff.json", {"provider": "opencode-go", "mode": "api", "copied_provider_count": 1,
                                       "routing_header_names": ["x-opencode-org-id"]})
    print(json.dumps({"provider": "opencode-go", "credential_mode": "api", "handoff": "complete"}))


def factory(workspace, evidence):
    return IsolatedOpenCode(workspace, evidence, profile=profile(), image=IMAGE, image_id=IMAGE_ID)


def runner(max_model_turns=2):
    store = SkillStore(STATE / "skills")
    def pin(name, source):
        try:
            value = store.import_skill(name, source)
        except ConflictError:
            value = store.revision(name)
        if value["tree_hash"] != tree_hash(inventory(source)):
            raise RuntimeError("fixture_revision_changed")
        return value
    imported = pin("laomedo-pilot", ROOT / "examples/skill-agent-pilot/skill")
    ref = {key: imported[key] for key in ("skill_id", "revision_id", "tree_hash")}
    _json(STATE / "skill-reference.json", ref)
    second = pin("laomedo-result-format", ROOT / "examples/opencode-agent/skill")
    refs = [ref, {key: second[key] for key in ("skill_id", "revision_id", "tree_hash")}]
    _json(STATE / "skill-references.json", {"skills": refs})
    obj = OpenCodeRunner(STATE / "runs-state", store.root, ROOT / "examples/skill-agent-pilot/source",
                         transport_factory=factory, max_model_turns=max_model_turns)
    return obj, ref


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=["setup", "auth", "serve", "fresh", "resume"])
    parser.add_argument("--approved-model-turn", action="store_true")
    parser.add_argument("--max-model-turns", type=int, default=2)
    parser.add_argument("--port", type=int, default=8768)
    args = parser.parse_args()
    if args.phase == "setup":
        setup()
    elif args.phase == "auth":
        auth()
    elif args.phase == "serve":
        from laomedo.local_runner import serve
        obj, _ = runner(args.max_model_turns)
        serve(obj, port=args.port).serve_forever()
    else:
        if not args.approved_model_turn:
            parser.error("explicit approval marker required")
        obj, ref = runner(args.max_model_turns)
        if args.phase == "fresh":
            value = obj.start({"task": "Load the laomedo-pilot skill using the native skill tool. Then use laomedo_exec to read /draft/fixture.txt and report its color and count. Use only the available tools.",
                               "model": "opencode-go/gpt-6-luna", "effort": "default", "skill_ref": ref})
            _json(STATE / "first-run-reference.json", {"run_id": value["run_id"]})
        else:
            previous = json.loads((STATE / "first-run-reference.json").read_text())
            prior = obj.status(previous["run_id"])
            value = obj.resume(prior["run_id"], "Use laomedo_exec to read /draft/fixture.txt again and report the same color/count. Keep this native session.",
                expected_post_run_hash=prior["post_run_hash"], expected_thread_id=prior["thread_id"],
                model="opencode-go/gpt-6-luna", effort="default")
        print(json.dumps({key: value.get(key) for key in
              ("run_id", "provider", "thread_id", "status", "error_category", "answer", "post_run_hash", "attempt_number")}))


if __name__ == "__main__":
    main()
