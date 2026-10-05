"""Create and inspect a draft model-egress sidecar without starting it."""

import json
from pathlib import Path
import secrets

from probe_create_only import docker
from probe_stage import inspect, sidecar_evidence


HERE = Path(__file__).resolve().parent
IMAGE = "laomedo-exp18-model-egress:local"
IMAGE_ID = "sha256:4c07cc92871f1cd80c9f8f0615e17815aa9e95c141c90854c8598a0939a5ada3"
OBSERVATION = HERE / "model-egress-create-observation.json"


def extra_errors(item, expected_env):
    host = item["HostConfig"]
    config = item["Config"]
    errors = []
    if host.get("PidsLimit") != 64 or host.get("Memory") != 128 * 1024 * 1024:
        errors.append("sidecar_resource_limit_mismatch")
    if host.get("RestartPolicy") != {"Name": "no", "MaximumRetryCount": 0}:
        errors.append("sidecar_restart_policy_mismatch")
    for key in ("Binds", "Mounts", "Tmpfs", "ExtraHosts", "Links", "Dns",
                "GroupAdd", "Sysctls", "Devices", "DeviceRequests"):
        if host.get(key) not in (None, [], {}):
            errors.append("sidecar_unexpected_" + key.lower())
    for key in ("PidMode", "IpcMode", "UTSMode", "UsernsMode"):
        if host.get(key) not in (None, "", "private"):
            errors.append("sidecar_unexpected_" + key.lower())
    if config.get("WorkingDir") != "" or config.get("Cmd") is not None:
        errors.append("sidecar_command_mismatch")
    if config.get("Env") != expected_env:
        errors.append("sidecar_environment_mismatch")
    if config.get("Volumes"):
        errors.append("sidecar_volume_mismatch")
    return errors


def main():
    nonce = secrets.token_hex(6)
    network = "laomedo-exp18-egress-" + nonce
    container = "laomedo-exp18-egress-" + nonce
    report = {"purpose": "create_only_no_model", "stage_starts": 0,
              "model_turns": 0, "network": "internal_plus_bridge",
              "image_id_expected": IMAGE_ID, "errors": [], "cleanup_complete": False}
    created_network = False
    created_container = False
    try:
        report["docker_engine"] = docker(
            "version", "--format", "{{.Server.Version}}").stdout.strip()
        observed_id = docker("image", "inspect", IMAGE, "--format", "{{.Id}}").stdout.strip()
        if observed_id != IMAGE_ID:
            raise RuntimeError("sidecar_image_id_mismatch")
        image_config = json.loads(docker("image", "inspect", IMAGE,
                                        "--format", "{{json .Config}}").stdout)
        docker("network", "create", "--internal", network)
        created_network = True
        docker("create", "--pull=never", "--name", container,
               "--network", network, "--read-only", "--cap-drop=ALL",
               "--security-opt=no-new-privileges", "--pids-limit=64",
               "--memory=128m", "--user=10001:10001", IMAGE)
        created_container = True
        docker("network", "connect", "bridge", container)
        item = inspect(container)
        evidence = sidecar_evidence(
            item, network, expected_image=IMAGE_ID,
            expected_entrypoint=["python", "-B", "-u", "/app/proxy.py"])
        evidence["errors"].extend(extra_errors(item, image_config.get("Env")))
        evidence["pids_limit"] = item["HostConfig"].get("PidsLimit")
        evidence["memory_limit"] = item["HostConfig"].get("Memory")
        evidence["status"] = item["State"]["Status"]
        if evidence["status"] != "created":
            evidence["errors"].append("sidecar_started_unexpectedly")
        report["inspect"] = evidence
        report["errors"].extend(evidence["errors"])
    except (RuntimeError, KeyError, ValueError) as exc:
        report["errors"].append(str(exc))
    finally:
        if created_container:
            docker("rm", "-f", container, check=False)
        if created_network:
            docker("network", "rm", network, check=False)
        report["cleanup_complete"] = (
            docker("inspect", container, check=False).returncode != 0 and
            docker("network", "inspect", network, check=False).returncode != 0)
        report["passed"] = not report["errors"] and report["cleanup_complete"]
        OBSERVATION.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"passed": report["passed"], "errors": report["errors"],
                          "stage_starts": 0, "model_turns": 0,
                          "cleanup_complete": report["cleanup_complete"]}))
        if not report["passed"]:
            raise SystemExit(1)


if __name__ == "__main__":
    main()
