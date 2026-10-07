"""End-to-end split LocalRunner probe using a fake Responses server.

No OpenAI credential or model turn is used. The disposable controller profile
is removed only after both LocalRunner instances and their containers exit.
"""

import ast
import json
from pathlib import Path
import secrets
import subprocess
import tempfile

from laomedo.local_runner import LocalRunner, RunnerError, SPLIT_TOOLS, _split_profile
from laomedo.siwc_auth import ChatGPTConnection, NEEDED
from laomedo.skill_store import SkillStore
from probe_mock_responses import MockResponses


def probe():
    with tempfile.TemporaryDirectory(prefix="laomedo-107-runner-") as directory:
        root = Path(directory)
        state = root / "state"
        auth_state = root / "auth"
        access_canary = "SYNTHETIC_" + secrets.token_hex(16)
        refresh_canary = "SYNTHETIC_" + secrets.token_hex(16)
        file_canary = "FILE_" + secrets.token_hex(16)
        profile = _split_profile(state.resolve())
        skill_source = root / "skill-source"
        skill_source.mkdir()
        (skill_source / "SKILL.md").write_text(
            "---\nname: split-probe\n---\nUse the pinned fixture.\n",
            encoding="utf-8")
        store = SkillStore(root / "skill-store")
        revision = store.import_skill("split-probe", skill_source)
        source = Path(__file__).resolve().parents[3] / "tests"
        command = ("sh -c 'if test -n \"${ACCESS_TOKEN+x}\"; "
                   "then printf readable; else printf absent; fi "
                   "> /draft/token-observation.txt; "
                   "if tr \"\\000\" \"\\n\" </proc/1/environ | "
                   "grep -q \"^ACCESS_TOKEN=\"; then printf readable; "
                   "else printf absent; fi > /draft/process-observation.txt; "
                   "if test -r /home/runner/.codex/probe.secret; "
                   "then printf readable; else printf absent; fi "
                   "> /draft/file-observation.txt; "
                   "printf remote >> /draft/runner-marker.txt'")
        script = ("const result = await tools.exec_command({cmd: " +
                  json.dumps(command) + ", workdir: '/draft'}); " +
                  "text(result.exit_code); " +
                  "text('TOOLS:' + JSON.stringify(ALL_TOOLS.map(t => t.name).sort()));")
        try:
            with MockResponses(tool_input=script, tool_request_numbers=(1, 3, 5)) as mock:
                provider = (
                    'model_provider="laomedo_mock"',
                    'model_providers.laomedo_mock.name="Laomedo Mock"',
                    'model_providers.laomedo_mock.base_url="' + mock.base_url + '"',
                    'model_providers.laomedo_mock.env_key="ACCESS_TOKEN"',
                    'model_providers.laomedo_mock.wire_api="responses"',
                    'model_providers.laomedo_mock.requires_openai_auth=false',
                    'model_providers.laomedo_mock.supports_websockets=false',
                )
                connection = ChatGPTConnection(auth_state)
                attempt = connection.begin("http://127.0.0.1:1455/auth/callback")
                connection.finish(attempt, {"code": "synthetic-code",
                    "state": attempt["state"], "client_id": "oaiapp_fixture"},
                    exchange=lambda _url, fields: {
                        "id_token": "synthetic-id",
                        "access_token": access_canary,
                        "refresh_token": refresh_canary,
                        "scope": " ".join(sorted(NEEDED)),
                        "expires_in": 3600},
                    verify=lambda _token, _client, _nonce: {
                        "iss": "https://auth.openai.com", "sub": "fixture-subject"})
                # Use the real broker path; only the endpoint is replaced by
                # the local fake Responses server for this credential-free run.
                options = dict(split_executor=True, auth_store=auth_state,
                               max_model_turns=3)
                request = {"task": "Synthetic fixture", "model": "gpt-6-luna",
                           "effort": "low", "skill_ref": {
                               "skill_id": "split-probe",
                               "revision_id": revision["revision_id"],
                               "tree_hash": revision["tree_hash"]}}
                first_runner = LocalRunner(state, store.root, source, **options)
                first_runner.split_provider_config = provider
                writer = subprocess.run(["docker", "run", "--rm", "--pull=never",
                    "--network", "none", "--user", "10001:10001", "--mount",
                    f"type=volume,source={profile},target=/home/runner/.codex",
                    "laomedo-codex-boundary:0.159.2", "sh", "-c",
                    "printf %s " + file_canary +
                    " > /home/runner/.codex/probe.secret"],
                    capture_output=True, timeout=15)
                if writer.returncode:
                    raise RuntimeError("controller_file_canary_setup_failed")
                first = first_runner.start(request)
                if first["status"] != "completed":
                    raise RuntimeError("first_split_turn_incomplete:" +
                                       str(first.get("error_category")))
                first_workspace = state / "runs" / first["run_id"] / "workspace"
                first_observation = (first_workspace / "token-observation.txt").read_text()
                first_process = (first_workspace / "process-observation.txt").read_text()
                first_file = (first_workspace / "file-observation.txt").read_text()
                resumed = first_runner.resume(
                    first["run_id"], "Synthetic same-runner continuation",
                    expected_post_run_hash=first["post_run_hash"],
                    expected_thread_id=first["thread_id"],
                    model="gpt-6-luna", effort="low")
                resumed_marker = (first_workspace / "runner-marker.txt").read_text()
                second_runner = LocalRunner(state, store.root, source, **options)
                second_runner.split_provider_config = provider
                old_run_refused = False
                try:
                    second_runner.resume(
                        resumed["run_id"], "Synthetic restart fixture",
                        expected_post_run_hash=resumed["post_run_hash"],
                        expected_thread_id=resumed["thread_id"],
                        model="gpt-6-luna", effort="low")
                except RunnerError as exc:
                    old_run_refused = str(exc) == "resume_after_runner_restart_forbidden"
                second = second_runner.start(request)
                workspace = state / "runs" / second["run_id"] / "workspace"
                observation = (workspace / "token-observation.txt").read_text()
                process_observation = (workspace / "process-observation.txt").read_text()
                file_observation = (workspace / "file-observation.txt").read_text()
                marker = (workspace / "runner-marker.txt").read_text()
                ledger = json.loads((state / "turn-ledger.json").read_text())
                observed_tools = set()
                for request in mock.requests:
                    for output in request["tool_outputs"]:
                        try:
                            blocks = ast.literal_eval(output)
                        except (ValueError, SyntaxError):
                            continue
                        for block in blocks if isinstance(blocks, list) else []:
                            value = block.get("text") if isinstance(block, dict) else None
                            if isinstance(value, str) and value.startswith("TOOLS:"):
                                observed_tools = set(json.loads(value[6:]))
                exposure_files = [str(path.relative_to(state))
                    for path in state.rglob("*") if path.is_file() and
                    (access_canary.encode() in path.read_bytes() or
                     refresh_canary.encode() in path.read_bytes())]
                trace_clean = not exposure_files
                profile_archive = subprocess.run(["docker", "run", "--rm",
                    "--pull=never", "--network", "none", "--user", "10001:10001",
                    "--mount", f"type=volume,source={profile},target=/profile,readonly",
                    "laomedo-codex-boundary:0.159.2", "tar", "-cf", "-",
                    "-C", "/", "profile"], capture_output=True, timeout=15)
                if profile_archive.returncode:
                    raise RuntimeError("controller_profile_scan_failed")
                profile_clean = (access_canary.encode() not in profile_archive.stdout and
                                 refresh_canary.encode() not in profile_archive.stdout)
                result = {
                    "schema_version": 1,
                    "real_model_turns": 0,
                    "synthetic_turns": ledger["attempted_turns"],
                    "fake_responses_requests": len(mock.requests),
                    "first_status": first["status"],
                    "same_runner_resume_status": resumed["status"],
                    "same_native_thread_on_resume": first["thread_id"] ==
                        resumed["thread_id"],
                    "new_run_after_restart_status": second["status"],
                    "old_run_resume_refused": old_run_refused,
                    "new_native_thread_after_restart": first["thread_id"] !=
                        second["thread_id"],
                    "same_nonsecret_credential_ref": first["credential"] ==
                        second["credential"],
                    "controller_token_absent_from_executor":
                        first_observation == "absent" and observation == "absent",
                    "controller_process_absent_from_executor":
                        first_process == "absent" and process_observation == "absent",
                    "controller_file_absent_from_executor":
                        first_file == "absent" and file_observation == "absent",
                    "tokens_absent_from_controller_profile": profile_clean,
                    "secret_absent_from_run_state": trace_clean,
                    "secret_exposure_files": exposure_files,
                    "tool_surface_exact": observed_tools == SPLIT_TOOLS,
                    "agent_commands_ran_three_times":
                        resumed_marker == "remoteremote" and marker == "remote",
                    "answer": second.get("answer"),
                }
                if (resumed["status"] != "completed" or
                        second["status"] != "completed" or
                        result["synthetic_turns"] != 3 or
                        result["fake_responses_requests"] != 6 or
                        not result["same_native_thread_on_resume"] or
                        not result["old_run_resume_refused"] or
                        not result["new_native_thread_after_restart"] or
                        not result["same_nonsecret_credential_ref"] or
                        not result["controller_token_absent_from_executor"] or
                        not result["controller_process_absent_from_executor"] or
                        not result["controller_file_absent_from_executor"] or
                        not result["tokens_absent_from_controller_profile"] or
                        not result["secret_absent_from_run_state"] or
                        not result["tool_surface_exact"] or
                        not result["agent_commands_ran_three_times"]):
                    raise RuntimeError("split_runner_probe_failed:" +
                                       json.dumps(result, sort_keys=True))
                return result
        finally:
            subprocess.run(["docker", "volume", "rm", profile],
                           capture_output=True, timeout=15)


if __name__ == "__main__":
    print(json.dumps(probe(), sort_keys=True))
