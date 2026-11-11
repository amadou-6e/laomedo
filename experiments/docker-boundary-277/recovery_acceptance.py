"""Real Docker owner-process loss, exact receipt recovery and isolation controls."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--implementation", type=Path, required=True)
    parser.add_argument("--child", choices=("session", "job"))
    parser.add_argument("--directory", type=Path)
    parser.add_argument("--endpoint")
    parser.add_argument("--image")
    parser.add_argument("--name")
    args = parser.parse_args()
    sys.path.insert(0, str(args.implementation / "src"))
    from laomedo.docker import DockerRuntime
    from py_docker.containers.models import ContainerSpec
    from py_docker.sessions.models import ContainerSession
    from py_docker.jobs.models import ContainerJob
    from py_docker.streams.models import StreamLimits
    from py_docker.errors import ReceiptInUseError, CleanupUnconfirmedError
    from docker.errors import NotFound

    def spec(image, name):
        return ContainerSpec(
            image=image,
            name=name,
            entrypoint=["/bin/sh"],
            command=["-c", "sleep 240"],
            user="10001:10001",
            network_mode="none",
            read_only=True,
            cap_drop=["ALL"],
        )

    if args.child:
        with DockerRuntime({"DOCKER_HOST": args.endpoint}).client() as client:
            request = dict(
                spec=spec(args.image, args.name),
                limits=StreamLimits(seconds=260, max_bytes=4096),
                receipt_path=args.directory / (args.child + ".json"),
            )
            if args.child == "session":
                with DockerRuntime.session(client, ContainerSession(**request)):
                    (args.directory / "session-ready").write_text("ready")
                    time.sleep(240)
            else:
                DockerRuntime.execute_job(
                    client, ContainerJob(**request, wait_timeout_seconds=10.0)
                )
        return

    from laomedo.agents.agents.claude.settings import IMAGE
    from laomedo.host.private_state.utils import prepare_private_directory
    from laomedo.host.private_state.models import DirectoryPermissionPolicy
    from laomedo.host.private_state.windows import WindowsDirectorySecurity

    temporary = tempfile.TemporaryDirectory(prefix="laomedo-recovery-acceptance-")
    root = Path(temporary.name)
    private = root / "private"
    system = WindowsDirectorySecurity().system_directory()
    environment = {
        name: value
        for name, value in os.environ.items()
        if name.upper()
        in {"SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "TEMP", "TMP", "PATHEXT", "PATH"}
    }
    prepare_private_directory(
        private,
        policy=DirectoryPermissionPolicy(
            whoami=system / "whoami.exe",
            icacls=system / "icacls.exe",
            environment=environment,
            deadline=time.monotonic() + 60,
        ),
    )
    children = []
    sentinel = None
    successful = False
    try:
        with DockerRuntime(None).client() as client:
            endpoint = client.connection.endpoint
            image = DockerRuntime.ensure_image(client, IMAGE)
            print(
                json.dumps(
                    {"stage": "admission", "image_id": image, "model_prompts": 0}
                ),
                flush=True,
            )
            sentinel = DockerRuntime.start_session(
                client,
                ContainerSession(
                    spec=spec(image, "laomedo-recovery-sentinel-" + uuid4().hex),
                    limits=StreamLimits(seconds=300, max_bytes=4096),
                    receipt_path=private / "sentinel.json",
                ),
            )
            try:
                for kind in ("session", "job"):
                    name = "laomedo-recovery-" + kind + "-" + uuid4().hex
                    log = (private / (kind + ".log")).open("wb")
                    child = subprocess.Popen(
                        [
                            sys.executable,
                            str(Path(__file__).resolve()),
                            "--implementation",
                            str(args.implementation),
                            "--child",
                            kind,
                            "--directory",
                            str(private),
                            "--endpoint",
                            endpoint,
                            "--image",
                            image,
                            "--name",
                            name,
                        ],
                        stdout=log,
                        stderr=log,
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    children.append((child, log, kind))
                    receipt = private / (kind + ".json")
                    deadline = time.monotonic() + 45
                    while True:
                        if child.poll() is not None:
                            raise RuntimeError("owner_exited_before_observation")
                        try:
                            observed = client.sdk.containers.get(name)
                            running = observed.attrs["State"]["Running"]
                        except NotFound:
                            running = False
                        if (
                            running
                            and receipt.exists()
                            and (
                                kind != "session"
                                or (private / "session-ready").exists()
                            )
                        ):
                            break
                        if time.monotonic() >= deadline:
                            raise RuntimeError("owner_start_not_observed")
                        time.sleep(0.1)
                    identity = observed.id
                    active_refused = False
                    try:
                        DockerRuntime.recover_receipts(client, [receipt], kind=kind)
                    except ReceiptInUseError:
                        active_refused = True
                    if not active_refused or not receipt.exists():
                        raise RuntimeError("live_receipt_ownership_not_preserved")
                    child.terminate()
                    child.wait(timeout=15)
                    log.close()
                    survived = client.sdk.containers.get(identity).attrs["State"][
                        "Running"
                    ]
                    if not survived:
                        raise RuntimeError("orphan_not_observed_after_owner_loss")
                    retained = json.loads(receipt.read_text())
                    conflict = private / (kind + "-wrong-owner.json")
                    conflicting = json.loads(json.dumps(retained))
                    label = next(iter(conflicting["labels"]))
                    conflicting["labels"][label] = "unrelated-owner-" + uuid4().hex
                    conflict.write_text(json.dumps(conflicting))
                    ownership_refused = False
                    try:
                        DockerRuntime.recover_receipts(client, [conflict], kind=kind)
                    except CleanupUnconfirmedError:
                        ownership_refused = True
                    conflict_survived = client.sdk.containers.get(identity).attrs[
                        "State"
                    ]["Running"]
                    if (
                        not ownership_refused
                        or not conflict.exists()
                        or not conflict_survived
                    ):
                        raise RuntimeError("ownership_conflict_not_preserved")
                    conflict.unlink()
                    absent_copy = private / (kind + "-already-absent.json")
                    absent_copy.write_text(json.dumps(retained))
                    retained["endpoint"] = "unix:///unrelated-recovery-daemon.sock"
                    wrong = private / (kind + "-wrong-endpoint.json")
                    wrong.write_text(json.dumps(retained))
                    endpoint_refused = False
                    try:
                        DockerRuntime.recover_receipts(client, [wrong], kind=kind)
                    except CleanupUnconfirmedError:
                        endpoint_refused = True
                    if (
                        not endpoint_refused
                        or not wrong.exists()
                        or not receipt.exists()
                    ):
                        raise RuntimeError("endpoint_mismatch_not_preserved")
                    endpoint_container_untouched = client.sdk.containers.get(
                        identity
                    ).attrs["State"]["Running"]
                    if not endpoint_container_untouched:
                        raise RuntimeError("wrong_endpoint_changed_container")
                    wrong.unlink()
                    DockerRuntime.recover_receipts(client, [receipt], kind=kind)
                    try:
                        client.sdk.containers.get(identity)
                        absent = False
                    except NotFound:
                        absent = True
                    DockerRuntime.recover_receipts(client, [receipt], kind=kind)
                    DockerRuntime.recover_receipts(client, [absent_copy], kind=kind)
                    absent_cleared = not absent_copy.exists()
                    if not absent_cleared:
                        raise RuntimeError("already_absent_receipt_not_cleared")
                    foreign_alive = client.sdk.containers.get(
                        sentinel.identity.id
                    ).attrs["State"]["Running"]
                    checks = {
                        "stage": kind + "_owner_loss",
                        "endpoint_sha256": hashlib.sha256(
                            endpoint.encode()
                        ).hexdigest(),
                        "exact_owned_id": identity,
                        "sentinel_id": sentinel.identity.id,
                        "wrong_labels_refused_and_retained": ownership_refused,
                        "conflicting_container_untouched": conflict_survived,
                        "already_absent_receipt_cleared": absent_cleared,
                        "active_owner_refused": active_refused,
                        "owner_terminated": child.poll() is not None,
                        "orphan_observed_running": survived,
                        "wrong_endpoint_refused_and_retained": endpoint_refused,
                        "wrong_endpoint_container_untouched": endpoint_container_untouched,
                        "exact_container_absent": absent,
                        "receipt_removed": not receipt.exists(),
                        "repeat_recovery_ok": True,
                        "foreign_sentinel_still_running": foreign_alive,
                    }
                    print(json.dumps(checks), flush=True)
                    if not absent or receipt.exists() or not foreign_alive:
                        raise RuntimeError("exact_recovery_not_confirmed")
            finally:
                for child, log, kind in children:
                    if child.poll() is None:
                        child.terminate()
                        child.wait(timeout=15)
                    log.close()
                    DockerRuntime.recover_receipts(
                        client, [private / (kind + ".json")], kind=kind
                    )
                DockerRuntime.close_session(sentinel)
                print(
                    json.dumps(
                        {
                            "stage": "sentinel_cleanup",
                            "confirmed": sentinel.cleanup_confirmed,
                        }
                    ),
                    flush=True,
                )
            successful = True
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
                    {"stage": "failed_private_state_retained", "directory": str(root)}
                ),
                flush=True,
            )


if __name__ == "__main__":
    main()
