"""EXP-18 steps 3-4: bounded no-model stage and sidecar probe."""

import hashlib
import json
from pathlib import Path
import secrets
import shutil
import socket
import sys
import tempfile
import threading
import time

from preflight import validate_host_roots, validate_inspect
from probe_create_only import (ENGINE_VERSION, HERE, IMAGE,
                               IMAGE_ID, TMPFS, create_args, docker)


ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT))
from laomedo.local_runner import LocalRunner, RunnerError, _hash_tree, serve  # noqa: E402


SIDE_IMAGE = "laomedo-exp18-sidecar:local"
SIDE_ID = "sha256:cb476dfe5717f9a6a37795c22b24e93892ccbfde2873c3cda109268e131a47e3"
CANARY_IMAGE = "laomedo-exp18-canary:local"
CANARY_ID = "sha256:502b45f6af95045522f9ea8e9da6f28c197263d2216bc57cd2828dfbf76b13d1"
RUNNER_PORT = 8767
BASE = ROOT / ".tools.local" / "exp18-stage"
OBSERVATION = HERE / "stage-observation.json"
REFUSAL = HERE / "stage-refusal.json"


def image_id(name):
    return docker("image", "inspect", name, "--format", "{{.Id}}").stdout.strip()


def inspect(name):
    return json.loads(docker("inspect", name).stdout)[0]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sidecar_evidence(item, network, *, expected_image=SIDE_ID,
                     expected_entrypoint=None):
    host = item["HostConfig"]
    config = item["Config"]
    networks = set(item["NetworkSettings"]["Networks"])
    errors = []
    if expected_entrypoint is None:
        expected_entrypoint = ["python", "-B", "-u", "/app/probe.py"]
    if item["Image"] != expected_image:
        errors.append("sidecar_image_mismatch")
    if networks != {network, "bridge"}:
        errors.append("sidecar_network_set_mismatch")
    if host.get("NetworkMode") != network:
        errors.append("sidecar_primary_network_mismatch")
    if item.get("Mounts") or host.get("Binds") or host.get("Mounts") or config.get("Volumes"):
        errors.append("sidecar_mount_present")
    if (host.get("PortBindings") or item["NetworkSettings"].get("Ports") or
            host.get("PublishAllPorts")):
        errors.append("sidecar_published_port")
    if host.get("ReadonlyRootfs") is not True or host.get("CapDrop") != ["ALL"]:
        errors.append("sidecar_filesystem_or_capabilities")
    if host.get("CapAdd") not in (None, []) or host.get("Privileged") is not False:
        errors.append("sidecar_privilege")
    if host.get("Devices") not in (None, []) or host.get("DeviceRequests") not in (None, []):
        errors.append("sidecar_device")
    if host.get("SecurityOpt") not in (["no-new-privileges"],
                                       ["no-new-privileges:true"]):
        errors.append("sidecar_no_new_privileges")
    if config.get("User") != "10001:10001":
        errors.append("sidecar_user")
    if config.get("Entrypoint") != expected_entrypoint:
        errors.append("sidecar_entrypoint")
    return {"image_id": item["Image"], "networks": sorted(networks),
            "published_ports": host.get("PortBindings"),
            "mount_count": len(item.get("Mounts") or []),
            "read_only_root": host.get("ReadonlyRootfs"),
            "cap_drop": host.get("CapDrop"),
            "cap_add": host.get("CapAdd"),
            "security_options": host.get("SecurityOpt"),
            "user": config.get("User"),
            "entrypoint": config.get("Entrypoint"), "errors": errors}


def config_errors(item, grant):
    config = item["Config"]
    expected_names = {entry.split("=", 1)[0] for entry in
                      json.loads(docker("image", "inspect", IMAGE,
                                         "--format", "{{json .Config.Env}}").stdout)}
    expected_names.add("CANARY_GRANT")
    names = {entry.split("=", 1)[0] for entry in config.get("Env") or []}
    errors = []
    if names != expected_names or len(config.get("Env") or []) != len(names):
        errors.append("config_env_names_mismatch")
    if config.get("Cmd") != ["sh", "-c", "sleep 45"]:
        errors.append("config_command_mismatch")
    if config.get("Entrypoint") != ["docker-entrypoint.sh"]:
        errors.append("config_entrypoint_mismatch")
    if config.get("WorkingDir") != "/draft":
        errors.append("config_workdir_mismatch")
    if not any(entry == "CANARY_GRANT=" + grant for entry in config.get("Env") or []):
        errors.append("config_grant_mismatch")
    return errors, sorted(names)


def sidecar_ready(network):
    code = ("import urllib.request,urllib.error; "
            "u='http://runner-probe:8098/runner-auth-probe'; "
            "\ntry: urllib.request.urlopen(u,timeout=3); print('unexpected')"
            "\nexcept urllib.error.HTTPError as e: print(e.code)")
    result = docker("run", "--rm", "--pull=never", "--network", network,
                    "--entrypoint", "python", CANARY_IMAGE, "-c", code)
    return result.stdout.strip() == "401"


def revoke(canary):
    code = ("import os,urllib.request; "
            "r=urllib.request.Request('http://127.0.0.1:8099/revoke',"
            "data=b'x',method='POST',headers={'X-Test-Grant':os.environ['CANARY_GRANT']});"
            "print(urllib.request.urlopen(r,timeout=3).status)")
    return docker("exec", canary, "python", "-c", code, check=False).stdout.strip() == "200"


def canary_status(canary):
    code = ("import json,urllib.request; "
            "print(urllib.request.urlopen('http://127.0.0.1:8099/status',"
            "timeout=3).read().decode())")
    for _ in range(20):
        result = docker("exec", canary, "python", "-c", code, check=False)
        if result.returncode == 0:
            return json.loads(result.stdout)
        time.sleep(0.1)
    raise RuntimeError("canary_status_unavailable")


def post_revoke_status(canary):
    code = ("import os,urllib.request,urllib.error; "
            "r=urllib.request.Request('http://127.0.0.1:8099/write',"
            "data=b'x',method='POST',headers={'X-Test-Grant':os.environ['CANARY_GRANT']});"
            "\ntry: print(urllib.request.urlopen(r,timeout=3).status)"
            "\nexcept urllib.error.HTTPError as e: print(e.code)")
    return docker("exec", canary, "python", "-c", code).stdout.strip()


def main():
    if image_id(IMAGE) != IMAGE_ID or image_id(SIDE_IMAGE) != SIDE_ID or image_id(CANARY_IMAGE) != CANARY_ID:
        raise RuntimeError("image_id_mismatch")
    engine = docker("version", "--format", "{{.Server.Version}}").stdout.strip()
    if engine != ENGINE_VERSION:
        REFUSAL.write_text(json.dumps({"error_category": "engine_change",
                                      "expected_engine": ENGINE_VERSION,
                                      "observed_engine": engine,
                                      "stage_starts": 0, "model_turns": 0}, indent=2) + "\n",
                           encoding="utf-8")
        raise RuntimeError("engine_change:" + engine)
    with socket.socket() as sock:
        if sock.connect_ex(("127.0.0.1", RUNNER_PORT)) == 0:
            raise RuntimeError("runner_port_already_in_use")
    BASE.mkdir(parents=True, exist_ok=True)
    if not BASE.resolve().is_relative_to(ROOT.resolve()):
        raise RuntimeError("scratch_outside_workspace")
    nonce = secrets.token_hex(6)
    network = "laomedo-exp18-stage-" + nonce
    names = {role: "laomedo-exp18-" + role + "-" + nonce
             for role in ("sidecar", "canary", "stage")}
    token = secrets.token_hex(32)
    report = {"launcher_revision": "probe_stage.py", "docker_engine": engine,
              "stage_image_id": IMAGE_ID, "sidecar_image_id": SIDE_ID,
              "canary_image_id": CANARY_ID, "runner_port": RUNNER_PORT,
              "model_turns": 0, "grant_fingerprint": hashlib.sha256(token.encode()).hexdigest(),
              "stage_starts": 0}
    for name in names.values():
        if docker("inspect", name, check=False).returncode == 0:
            raise RuntimeError("container_name_collision")
    if docker("network", "inspect", network, check=False).returncode == 0:
        raise RuntimeError("network_name_collision")
    server = None
    thread = None
    with tempfile.TemporaryDirectory(prefix="laomedo-exp18-runner-") as private:
        with tempfile.TemporaryDirectory(prefix="fixture-", dir=BASE) as temp:
            root = Path(temp).resolve()
            roots = {role: root / role for role in ("checkout", "effective_skill",
                     "canonical_skill", "host", "runner_store", "credential_standin")}
            markers = {"names": [], "bytes": [], "paths": []}
            canaries = {}
            for role, directory in roots.items():
                directory.mkdir()
                name = role + "-" + secrets.token_hex(8) + ".txt"
                value = secrets.token_hex(24)
                path = directory / ("canary.txt" if role == "effective_skill" else name)
                path.write_text(value, encoding="utf-8")
                canaries[role] = path
                if role not in ("checkout", "effective_skill"):
                    markers["names"].append(name)
                    markers["bytes"].append(value)
                    mount_path = {"canonical_skill": "/canonical-skill",
                                  "runner_store": "/runner-store",
                                  "host": "/host-protected",
                                  "credential_standin": "/credential-standin"}[role]
                    markers["paths"].append(mount_path + "/" + name)
            shutil.copy2(HERE / "stage_probe.js", roots["checkout"] / "probe.js")
            before = {role: digest(path) for role, path in canaries.items()}
            if validate_host_roots(roots):
                raise RuntimeError("fixture_roots_invalid")
            try:
                runner = LocalRunner(Path(private) / "state", Path(private) / "skills",
                                     ROOT / "laomedo", check_docker=False, max_model_turns=0)
                server = serve(runner, port=RUNNER_PORT)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                report["runner_model_turn_cap"] = runner.max_model_turns
                docker("network", "create", "--internal", network)
                docker("create", "--pull=never", "--name", names["sidecar"],
                       "--network", network, "--network-alias", "runner-probe",
                       "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges",
                       "--user=10001:10001", SIDE_IMAGE)
                docker("network", "connect", "bridge", names["sidecar"])
                report["sidecar_prestart_inspect"] = sidecar_evidence(inspect(names["sidecar"]), network)
                if report["sidecar_prestart_inspect"]["errors"]:
                    raise RuntimeError("sidecar_prestart_refused")
                docker("start", names["sidecar"])
                report["sidecar_runner_401"] = sidecar_ready(network)
                if not report["sidecar_runner_401"]:
                    raise RuntimeError("sidecar_runner_401_unavailable")
                docker("create", "--pull=never", "--name", names["canary"],
                       "--network", network, "--network-alias", "canary",
                       "--tmpfs", "/canary-state:rw,nosuid,nodev,size=1m,mode=1777",
                       "--env", "CANARY_GRANT=" + token,
                       "--env", "CANARY_LEASE_NS=60000000000", CANARY_IMAGE)
                docker("start", names["canary"])
                report["lease_deadline_ns"] = canary_status(names["canary"])["expiry_ns"]
                expected = {"/draft": ("bind", str(roots["checkout"]), True),
                            "/skills": ("bind", str(roots["effective_skill"]), False)}
                docker(*create_args(names["stage"], network, roots, grant=token,
                                    command=["sh", "-c", "sleep 45"]))
                stage = inspect(names["stage"])
                report["stage_prestart_errors"] = validate_inspect(
                    stage, expected, network, IMAGE_ID, TMPFS)
                config_failures, env_names = config_errors(stage, token)
                report["stage_config_errors"] = config_failures
                report["stage_env_names"] = env_names
                report["stage_command"] = stage["Config"]["Cmd"]
                report["stage_id"] = stage["Id"][:16]
                if report["stage_prestart_errors"] or config_failures:
                    raise RuntimeError("stage_prestart_refused")
                docker("start", names["stage"])
                report["stage_starts"] = 1
                report["probe_start_ns"] = time.time_ns()
                run = docker("exec", "--env", "PROTECTED_MARKERS=" + json.dumps(markers),
                             names["stage"], "node", "/draft/probe.js", check=False)
                report["probe_exit_code"] = run.returncode
                report["probe_end_ns"] = time.time_ns()
                try:
                    report["probe"] = json.loads(run.stdout.strip().splitlines()[-1])
                except (ValueError, IndexError):
                    report["probe"] = {"parse_error": True, "stderr_class": "probe_failed"}
                docker("stop", "--time", "1", names["stage"])
                report["stage_stopped"] = inspect(names["stage"])["State"]["Status"] == "exited"
                report["grant_revoked"] = revoke(names["canary"])
                report["post_revoke_status"] = post_revoke_status(names["canary"])
                report["canary_revoked"] = canary_status(names["canary"])["revoked"]
                events = docker("exec", names["canary"], "cat", "/canary-state/events.jsonl",
                                check=False)
                report["canary_events"] = [json.loads(line) for line in events.stdout.splitlines()]
                try:
                    _hash_tree(roots["checkout"])
                    report["host_symlink_processing"] = "accepted"
                except RunnerError as exc:
                    report["host_symlink_processing"] = str(exc)
                report["protected_hashes"] = {
                    role: {"before": before[role], "after": digest(canaries[role])}
                    for role in ("checkout", "canonical_skill", "runner_store", "host",
                                 "credential_standin", "effective_skill")}
                report["protected_hashes_unchanged"] = all(
                    pair["before"] == pair["after"]
                    for pair in report["protected_hashes"].values())
            except Exception as exc:
                report["error"] = type(exc).__name__ + ":" + str(exc)[:120]
            finally:
                if names["canary"] and docker("inspect", names["canary"], check=False).returncode == 0:
                    report.setdefault("grant_revoked", revoke(names["canary"]))
                for role in ("stage", "canary", "sidecar"):
                    docker("rm", "-f", names[role], check=False)
                docker("network", "rm", network, check=False)
                report["cleanup_complete"] = (
                    all(docker("inspect", name, check=False).returncode != 0
                        for name in names.values()) and
                    docker("network", "inspect", network, check=False).returncode != 0)
                if server is not None:
                    server.shutdown()
                    server.server_close()
                if thread is not None:
                    thread.join(timeout=3)
            report["direct_boundary_pass"] = (
                "error" not in report and report["cleanup_complete"] and
                report.get("stage_stopped") and
                report.get("grant_revoked") and report.get("canary_revoked") and
                report.get("post_revoke_status") == "403" and
                report.get("probe_end_ns", 0) < report.get("lease_deadline_ns", 0) and
                report.get("protected_hashes_unchanged") and
                report.get("host_symlink_processing") == "unsafe_workspace_entry" and
                report.get("probe_exit_code") == 0 and
                report.get("probe", {}).get("checkout_write") and
                report.get("probe", {}).get("effective_skill_read") and
                report.get("probe", {}).get("skill_write") in ("EROFS", "EACCES") and
                report.get("probe", {}).get("canary_valid") == 200 and
                report.get("probe", {}).get("canary_invalid") == 403 and
                report.get("probe", {}).get("runner_probe") == 401 and
                not report.get("probe", {}).get("sweep", {}).get("found") and
                not report.get("probe", {}).get("sweep", {}).get("incomplete") and
                len(report.get("probe", {}).get("protected_paths", {})) == 8 and
                report.get("probe", {}).get("symlink_read") == "ENOENT" and
                all(value in ("ENOENT", "EACCES") for value in
                    report.get("probe", {}).get("protected_paths", {}).values()) and
                all(not isinstance(value, int) for value in
                    report.get("probe", {}).get("direct_routes", {}).values()))
    OBSERVATION.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report.get(key) for key in (
        "docker_engine", "sidecar_runner_401", "stage_prestart_errors",
        "stage_config_errors", "stage_starts", "probe_exit_code", "grant_revoked",
        "protected_hashes_unchanged", "host_symlink_processing",
        "cleanup_complete", "direct_boundary_pass", "error")}))
    if not report["direct_boundary_pass"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
