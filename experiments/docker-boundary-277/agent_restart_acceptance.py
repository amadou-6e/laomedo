"""Actual explicitly composed Agent owner loss and constructor reconciliation."""

import argparse
import hashlib
import os
import shutil
from urllib.request import Request, build_opener
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from uuid import uuid4


def remove_temporary_profile(root, provider, docker):
    """Remove only this generated experiment's profile, including on early failure."""
    root = root.resolve()
    if root.parent != Path(tempfile.gettempdir()).resolve() or not root.name.startswith(
        "laomedo-codex-restart-"
    ):
        raise RuntimeError("unexpected_experiment_cleanup_root")
    if provider == "codex":
        from laomedo.agents.agents.codex.utils import _split_profile

        profile = _split_profile(root / "runner")
        if docker.volumes.exists(profile):
            docker.sdk.volumes.get(profile).remove()
        return not docker.volumes.exists(profile)
    if provider != "opencode":
        raise RuntimeError("unexpected_experiment_provider")
    profile = root / "profile"
    if profile.is_symlink() or profile.resolve().parent != root:
        raise RuntimeError("unexpected_experiment_profile_path")
    if profile.exists():
        shutil.rmtree(profile)
    return not profile.exists()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation", type=Path, required=True)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--provider", choices=("codex", "opencode"), default="codex")
    args = parser.parse_args()
    sys.path.insert(0, str(args.implementation / "src"))
    from acceptance import session_login
    from laomedo.agents.agents.codex.agent import CodexAgent
    from laomedo.agents.errors import RunnerError
    from laomedo.docker import DockerRuntime
    from py_docker.containers.models import ContainerSpec
    from py_docker.sessions.models import ContainerSession
    from py_docker.streams.models import StreamLimits
    from docker.errors import NotFound

    def construct(root):
        if args.provider == "codex":
            return CodexAgent(
                root / "runner",
                root / "registry",
                root / "repository/source",
                **session_login(),
            )
        from laomedo.agents.agents.opencode.agent import OpenCodeAgent
        from laomedo.agents.agents.opencode.runtime import OpenCodeAgentRuntime

        def transport_factory(workspace, evidence):
            return OpenCodeAgentRuntime(workspace, evidence, profile=root / "profile")

        return OpenCodeAgent(
            root / "runner",
            root / "registry",
            root / "repository/source",
            transport_factory=transport_factory,
        )

    if args.child:
        agent = construct(args.root)
        models = agent.model_catalog(refresh=True)["models"]
        if args.provider == "codex":
            selected = next((m for m in models if "gpt-5" in m["id"]), models[0])
        else:
            selected = next(
                m
                for m in models
                if m["id"].startswith("opencode-go/") and "claude-haiku" in m["id"]
            )
        effort = "low" if "low" in selected.get("efforts", []) else "default"
        (args.root / "selection.json").write_text(
            json.dumps({"model": selected["id"], "effort": effort})
        )
        result = agent.start(
            {
                "task": "Use the shell to run: printf active > acceptance-active.txt; sleep 120. Wait for it to finish. This is a disposable acceptance workspace; do not edit other files or delegate.",
                "model": selected["id"],
                "effort": effort,
            }
        )
        print(
            json.dumps(
                {"stage": "unexpected_child_completion", "status": result["status"]}
            ),
            flush=True,
        )
        return

    temporary = tempfile.TemporaryDirectory(prefix="laomedo-codex-restart-")
    root = Path(temporary.name)
    owner = log = agent = sentinel = None
    successful = False
    try:
        source = root / "repository/source"
        source.mkdir(parents=True)
        subprocess.run(["git", "init", "--quiet", str(source.parent)], check=True)
        (source / "task.txt").write_text(
            "Disposable owner-loss acceptance workspace.\n"
        )
        if args.provider == "opencode":
            from laomedo.agents.agents.opencode.auth.utils import console_provider
            from laomedo.agents.agents.opencode.auth.transport import NoRedirect
            from laomedo.agents.agents.base.utils import _json
            from laomedo.host.private_state.utils import prepare_private_directory
            from laomedo.host.private_state.models import DirectoryPermissionPolicy
            from laomedo.host.private_state.windows import WindowsDirectorySecurity

            system = WindowsDirectorySecurity().system_directory()
            environment = {
                key: value
                for key, value in os.environ.items()
                if key.upper()
                in {
                    "SYSTEMROOT",
                    "WINDIR",
                    "SYSTEMDRIVE",
                    "TEMP",
                    "TMP",
                    "PATHEXT",
                    "PATH",
                }
            }
            prepare_private_directory(
                root / "profile",
                policy=DirectoryPermissionPolicy(
                    whoami=system / "whoami.exe",
                    icacls=system / "icacls.exe",
                    environment=environment,
                    deadline=time.monotonic() + 60,
                ),
            )

            def supported_config(url, headers):
                with build_opener(NoRedirect()).open(
                    Request(url, headers=headers), timeout=30
                ) as response:
                    remote = json.load(response)
                provider = remote["config"]["provider"]["opencode-go"]
                provider["models"] = {
                    name: value
                    for name, value in provider["models"].items()
                    if value.get("provider", {}).get("npm", "@ai-sdk/openai-compatible")
                    in {
                        "@ai-sdk/openai",
                        "@ai-sdk/openai-compatible",
                        "@ai-sdk/anthropic",
                    }
                }
                return remote

            credential, org, routing, validity = console_provider(
                Path.home() / ".local/share/opencode/opencode.db",
                fetch=supported_config,
                include_routing=True,
                include_expiry=True,
            )
            _json(root / "profile/auth.json", {"opencode-go": credential})
            _json(
                root / "profile/auth-validity.json",
                dict(
                    validity,
                    credential_sha256=hashlib.sha256(
                        credential["key"].encode()
                    ).hexdigest(),
                ),
            )
            _json(
                root / "profile/provider-options.json",
                {
                    "provider": {
                        "opencode-go": dict(
                            routing, options={"headers": {"x-opencode-org-id": org}}
                        )
                    }
                },
            )
            del credential, org, routing, validity
        with DockerRuntime(None).client() as docker:
            if args.provider == "codex":
                from laomedo.agents.agents.codex.settings import IMAGE
            else:
                from laomedo.agents.agents.opencode.settings import IMAGE

            image = DockerRuntime.ensure_image(docker, IMAGE)
            sentinel = DockerRuntime.start_session(
                docker,
                ContainerSession(
                    spec=ContainerSpec(
                        image=image,
                        name="laomedo-codex-restart-sentinel-" + uuid4().hex,
                        entrypoint=["/bin/sh"],
                        command=["-c", "sleep 300"],
                        user="10001:10001",
                        read_only=True,
                        network_mode="none",
                    ),
                    limits=StreamLimits(seconds=320, max_bytes=4096),
                    receipt_path=root / "sentinel.json",
                ),
            )
            try:
                log = (root / "owner.log").open("wb")
                owner = subprocess.Popen(
                    [
                        sys.executable,
                        str(Path(__file__).resolve()),
                        "--implementation",
                        str(args.implementation),
                        "--child",
                        "--provider",
                        args.provider,
                        "--root",
                        str(root),
                    ],
                    stdout=log,
                    stderr=log,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                deadline = time.monotonic() + 150
                record = None
                while time.monotonic() < deadline:
                    if owner.poll() is not None:
                        raise RuntimeError(
                            "agent_owner_finished_before_active_observation"
                        )
                    for candidate in (root / "runner/runs").glob("*/record.json"):
                        try:
                            current = json.loads(candidate.read_text())
                        except (OSError, ValueError):
                            continue
                        if (
                            current["status"] == "running"
                            and (
                                candidate.parent / "workspace/acceptance-active.txt"
                            ).exists()
                        ):
                            record = current
                            break
                    if record:
                        break
                    time.sleep(0.2)
                if not record:
                    raise RuntimeError("actual_model_command_not_observed")
                receipts = list((root / "runner/receipts").glob("*.json")) + list(
                    (root / "runner/runs").glob("*/docker-receipts/*.json")
                )
                identities = [
                    json.loads(path.read_text())["observed_id"] for path in receipts
                ]
                running_before = [
                    docker.sdk.containers.get(identity).attrs["State"]["Running"]
                    for identity in identities
                ]
                print(
                    json.dumps(
                        {
                            "stage": "active_native_execution",
                            "model_command_marker_observed": True,
                            "owned_receipt_count": len(receipts),
                            "owned_running_count": sum(running_before),
                            "provider": args.provider,
                            "split_mode_unsupervised": not record.get(
                                "container_ownership", {}
                            ).get("supervised", False),
                        }
                    ),
                    flush=True,
                )
                if len(receipts) != 2 or not all(running_before):
                    raise RuntimeError("controller_executor_not_both_observed_running")
                owner.terminate()
                owner.wait(timeout=15)
                log.close()
                observed_orphans = 0
                for identity in identities:
                    try:
                        observed_orphans += bool(
                            docker.sdk.containers.get(identity).attrs["State"][
                                "Running"
                            ]
                        )
                    except NotFound:
                        pass
                before_cancel = record.get("cancel_confirmed")
                agent = construct(root)
                after = agent.status(record["run_id"])
                absent = 0
                for identity in identities:
                    try:
                        docker.sdk.containers.get(identity)
                    except NotFound:
                        absent += 1
                selection = json.loads((root / "selection.json").read_text())
                refused = None
                try:
                    agent.resume(
                        record["run_id"],
                        "Do not dispatch a new task.",
                        expected_post_run_hash=record.get("post_run_hash")
                        or "not-a-completed-snapshot",
                        expected_thread_id=record["thread_id"],
                        **selection,
                    )
                except RunnerError as error:
                    refused = error.code
                page = agent.read_activity(
                    record["run_id"], record["activity_attempt_id"]
                )
                checks = {
                    "stage": "agent_restart_reconciliation",
                    "provider": args.provider,
                    "running_orphans_after_owner_exit": observed_orphans,
                    "record_status": after["status"],
                    "error": after.get("error_category"),
                    "cancel_confirmation_unchanged": after.get("cancel_confirmed")
                    == before_cancel,
                    "exact_owned_absent_count": absent,
                    "pending_receipts": len(
                        list((root / "runner/receipts").glob("*.json"))
                        + list((root / "runner/runs").glob("*/docker-receipts/*.json"))
                    ),
                    "foreign_sentinel_alive": docker.sdk.containers.get(
                        sentinel.identity.id
                    ).attrs["State"]["Running"],
                    "resume_refusal": refused,
                    "activity_closed": page.closed,
                    "activity_complete": page.complete,
                    "activity_reason": page.reason,
                }
                print(json.dumps(checks), flush=True)
                if (
                    after["status"] != "interrupted"
                    or absent != len(identities)
                    or checks["pending_receipts"]
                    or not checks["foreign_sentinel_alive"]
                    or refused != "resume_binding_mismatch"
                    or not checks["cancel_confirmation_unchanged"]
                ):
                    raise RuntimeError("agent_restart_reconciliation_failed")
            finally:
                try:
                    if owner and owner.poll() is None:
                        owner.terminate()
                        owner.wait(timeout=15)
                    if log:
                        log.close()
                    DockerRuntime.recover_receipts(
                        docker,
                        list((root / "runner/receipts").glob("*.json"))
                        + list((root / "runner/runs").glob("*/docker-receipts/*.json")),
                    )
                    DockerRuntime.close_session(sentinel)
                finally:
                    if args.provider == "codex":
                        removed = remove_temporary_profile(root, args.provider, docker)
                        print(
                            json.dumps(
                                {
                                    "stage": "temporary_profile_cleanup",
                                    "removed": removed,
                                }
                            ),
                            flush=True,
                        )
                        if not removed:
                            raise RuntimeError("temporary_profile_cleanup_unconfirmed")

        successful = True
    finally:
        try:
            if args.provider == "opencode":
                removed = remove_temporary_profile(root, args.provider, None)
                print(
                    json.dumps(
                        {"stage": "temporary_profile_cleanup", "removed": removed}
                    ),
                    flush=True,
                )
                if not removed:
                    raise RuntimeError("temporary_profile_cleanup_unconfirmed")
        except Exception:
            successful = False
            raise
        finally:
            if successful:
                temporary.cleanup()
                print(
                    json.dumps(
                        {"stage": "private_state_cleanup", "removed": not root.exists()}
                    ),
                    flush=True,
                )
            else:
                temporary._finalizer.detach()
                print(
                    json.dumps(
                        {
                            "stage": "failed_private_state_retained",
                            "directory": str(root),
                        }
                    ),
                    flush=True,
                )


if __name__ == "__main__":
    main()
