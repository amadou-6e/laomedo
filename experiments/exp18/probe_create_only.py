"""EXP-18 steps 1-2: create/inspect refusals, never start a stage."""

import json
from pathlib import Path
import secrets
import subprocess
import tempfile

from preflight import _host_config_projection, validate_host_roots, validate_inspect


HERE = Path(__file__).resolve().parent
BASE = HERE.parents[2] / ".tools.local" / "exp18-create"
IMAGE = "laomedo-codex-boundary:0.159.2"
IMAGE_ID = "sha256:7b79ce12be47d6c8262dd4043895112d204416bda5cd891d124775df55587239"
ENGINE_VERSION = "27.3.1"
TMPFS = {"/tmp": "rw,nosuid,nodev,size=16m"}


def docker(*args, check=True):
    result = subprocess.run(["docker", *args], capture_output=True, text=True,
                            timeout=40, check=False)
    if check and result.returncode:
        raise RuntimeError(f"docker {args[0]} failed: {result.stderr[-250:]}")
    return result


def create_args(name, network, roots, *, skill_writable=False, seccomp=None,
                grant=None, command=None):
    skill_mount = (f"type=bind,source={roots['effective_skill']},target=/skills" +
                   ("" if skill_writable else ",readonly"))
    args = ["create", "--pull=never", "--name", name, "--network", network,
            "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--cgroupns=private",
            "--pids-limit=128", "--memory=1g", "--user=10001:10001",
            "--tmpfs=/tmp:rw,nosuid,nodev,size=16m",
            "--mount", f"type=bind,source={roots['checkout']},target=/draft",
            "--mount", skill_mount]
    if seccomp is not None:
        args.extend(["--security-opt", "seccomp=" + str(seccomp)])
    if grant is not None:
        args.extend(["--env", "CANARY_GRANT=" + grant])
    return args + [IMAGE, *(command or ["sh", "-c", "true"])]


def safe_projection(inspected):
    host = inspected["HostConfig"]
    fields = ("ReadonlyRootfs", "CapDrop", "CapAdd", "SecurityOpt",
              "PidMode", "IpcMode", "UTSMode", "UsernsMode", "Devices",
              "DeviceRequests", "Tmpfs", "NetworkMode", "PidsLimit",
              "Memory", "Privileged", "MaskedPaths", "ReadonlyPaths",
              "CgroupnsMode", "GroupAdd", "Sysctls", "ExtraHosts",
              "Ulimits", "OomKillDisable", "MemorySwap")
    return {"Image": inspected["Image"], "Config.User": inspected["Config"]["User"],
            "HostConfig": {field: host.get(field) for field in fields},
            "Mounts": [{key: mount.get(key) for key in
                        ("Destination", "Type", "RW", "Propagation")}
                       for mount in inspected.get("Mounts", [])]}


def normalized_host_config(inspected, roots, network):
    expected = {"/draft": ("bind", str(roots["checkout"]), True),
                "/skills": ("bind", str(roots["effective_skill"]), False)}
    return _host_config_projection(inspected["HostConfig"], expected, network)


def main():
    BASE.mkdir(parents=True, exist_ok=True)
    if not BASE.resolve().is_relative_to(HERE.parents[2].resolve()):
        raise RuntimeError("scratch_outside_workspace")
    nonce = secrets.token_hex(6)
    network = "laomedo-exp18-create-" + nonce
    names = ["laomedo-exp18-correct-" + nonce,
             "laomedo-exp18-writable-" + nonce,
             "laomedo-exp18-seccomp-" + nonce]
    if docker("image", "inspect", IMAGE, "--format", "{{.Id}}").stdout.strip() != IMAGE_ID:
        raise RuntimeError("image_id_mismatch")
    if any(docker("inspect", name, check=False).returncode == 0 for name in names):
        raise RuntimeError("container_name_collision")
    if docker("network", "inspect", network, check=False).returncode == 0:
        raise RuntimeError("network_name_collision")

    report = {"model_turns": 0, "stage_starts": 0, "dispatch_attempts": 0,
              "image_id": IMAGE_ID, "docker_engine": docker("version", "--format",
              "{{.Server.Version}}").stdout.strip()}
    if report["docker_engine"] != ENGINE_VERSION:
        raise RuntimeError("unreviewed_docker_engine")
    with tempfile.TemporaryDirectory(prefix="fixture-", dir=BASE) as temp:
        root = Path(temp).resolve()
        if not root.is_relative_to(BASE.resolve()):
            raise RuntimeError("scratch_outside_workspace")
        roots = {role: root / role for role in ("checkout", "effective_skill",
                 "canonical_skill", "host", "runner_store", "credential_standin")}
        for path in roots.values():
            path.mkdir()
            (path / "canary.txt").write_text(secrets.token_hex(12), encoding="utf-8")
        report["root_errors"] = validate_host_roots(roots)
        if report["root_errors"]:
            raise RuntimeError("fixture_root_refused")
        expected = {"/draft": ("bind", str(roots["checkout"]), True),
                    "/skills": ("bind", str(roots["effective_skill"]), False)}
        try:
            docker("network", "create", "--internal", network)
            docker(*create_args(names[0], network, roots))
            correct = json.loads(docker("inspect", names[0]).stdout)[0]
            report["effective_inspect"] = safe_projection(correct)
            report["reviewed_hostconfig"] = normalized_host_config(correct, roots, network)
            report["correct_errors"] = validate_inspect(correct, expected, network,
                                                          IMAGE_ID, TMPFS)
            docker(*create_args(names[1], network, roots, skill_writable=True))
            writable = json.loads(docker("inspect", names[1]).stdout)[0]
            report["writable_skill_errors"] = validate_inspect(
                writable, expected, network, IMAGE_ID, TMPFS)
            failed = docker(*create_args(names[2], network, roots,
                           seccomp=root / "missing-seccomp.json"), check=False)
            report["missing_seccomp_create_failed"] = failed.returncode != 0
            report["missing_seccomp_container_absent"] = (
                docker("inspect", names[2], check=False).returncode != 0)
            report["seccomp_error_class"] = (
                "opening_seccomp_profile_failed" if "seccomp profile" in
                failed.stderr.lower() else "other")
        finally:
            for name in names:
                docker("rm", "-f", name, check=False)
            docker("network", "rm", network, check=False)
        report["cleanup_complete"] = (
            all(docker("inspect", name, check=False).returncode != 0 for name in names)
            and docker("network", "inspect", network, check=False).returncode != 0)
    report["passed"] = (
        not report["correct_errors"] and
        "mount_mismatch:/skills" in report["writable_skill_errors"] and
        report["missing_seccomp_create_failed"] and
        report["missing_seccomp_container_absent"] and report["cleanup_complete"])
    (HERE / "create-only-observation.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "docker_engine", "correct_errors", "writable_skill_errors",
        "missing_seccomp_create_failed", "missing_seccomp_container_absent",
        "stage_starts", "dispatch_attempts", "model_turns", "cleanup_complete", "passed")}))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
