"""One authorized native Codex turn followed by exact-profile rollout export."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation", type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.implementation / "src"))
    from acceptance import session_login
    from laomedo.agents.agents.codex.agent import CodexAgent
    from laomedo.agents.agents.codex.activity.rollout_export import export_rollout
    from laomedo.docker import DockerRuntime

    agent = None
    with tempfile.TemporaryDirectory(prefix="laomedo-rollout-acceptance-") as directory:
        root = Path(directory)
        source = root / "repository/source"
        source.mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet", str(source.parent)], check=True)
        (source / "task.txt").write_text("Acceptance marker: amber-277.\n")
        try:
            agent = CodexAgent(
                root / "runner", root / "registry", source, **session_login()
            )
            catalog = agent.model_catalog(refresh=True)
            models = catalog["models"]
            selected = next((m for m in models if "gpt-5" in m["id"]), models[0])
            effort = "low" if "low" in selected.get("efforts", []) else "default"
            result = agent.start(
                {
                    "task": "Read task.txt and reply only with the acceptance marker. Do not edit files or delegate.",
                    "model": selected["id"],
                    "effort": effort,
                }
            )
            answer_ok = "amber-277" in (result.get("answer") or "")
            print(
                json.dumps(
                    {
                        "stage": "native_fresh",
                        "status": result["status"],
                        "error": result.get("error_category"),
                        "answer_ok": answer_ok,
                        "model": selected["id"],
                        "effort": effort,
                    }
                ),
                flush=True,
            )
            if result["status"] != "completed" or not answer_ok:
                raise RuntimeError("native_execution_not_accepted")
            output = export_rollout(agent.state, result["run_id"])
            content = output.read_bytes()
            first = json.loads(content.splitlines()[0])
            receipts = list(output.parent.joinpath("rollout-receipts").glob("*.json"))
            valid = (
                first["type"] == "session_meta"
                and first["payload"]["id"] == result["thread_id"]
            )
            print(
                json.dumps(
                    {
                        "stage": "native_rollout_export",
                        "bytes": len(content),
                        "thread_identity_matches": valid,
                        "recorded_profile_used": result["profile"] == agent.profile,
                        "recorded_endpoint_present": bool(
                            result["container_ownership"]["docker_endpoint"]
                        ),
                        "pending_export_receipts": len(receipts),
                    }
                ),
                flush=True,
            )
            if not valid or receipts:
                raise RuntimeError("native_export_not_accepted")
        finally:
            if agent is not None:
                with DockerRuntime(agent.docker_environment).client() as client:
                    client.sdk.volumes.get(agent.profile).remove()
                    removed = not client.volumes.exists(agent.profile)
                print(
                    json.dumps(
                        {"stage": "temporary_profile_cleanup", "removed": removed}
                    ),
                    flush=True,
                )
                if not removed:
                    raise RuntimeError("temporary_profile_cleanup_not_confirmed")
    print(
        json.dumps({"stage": "private_state_cleanup", "removed": not root.exists()}),
        flush=True,
    )


if __name__ == "__main__":
    main()
