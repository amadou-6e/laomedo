"""Zero-model early setup failure controls; only synthetic credentials are used."""

from contextlib import redirect_stdout
from importlib.util import module_from_spec, spec_from_file_location
import io
import json
from pathlib import Path
import shutil
import sys
import tempfile
from unittest.mock import patch


def main():
    implementation = Path(sys.argv[1]).resolve()
    sys.path.insert(0, str(implementation / "src"))
    script = Path(__file__).with_name("agent_restart_acceptance.py")
    spec = spec_from_file_location("restart_failure_target", script)
    target = module_from_spec(spec)
    spec.loader.exec_module(target)
    from laomedo.agents.agents.base.utils import _json

    for phase in ("profile-write", "docker-open", "sentinel-start"):
        captured = io.StringIO()
        writes = []
        expected = "injected_" + phase

        def write(path, value):
            writes.append(path)
            if phase == "profile-write" and len(writes) == 2:
                raise OSError(expected)
            return _json(path, value)

        credential = (
            {"type": "api", "key": "SYNTHETIC-NO-CREDENTIAL"},
            "synthetic-org",
            {
                "api": "https://opencode.ai/inference/go/openai/v1",
                "npm": "@ai-sdk/openai-compatible",
                "models": {},
            },
            {"credential_mode": "provider_key", "expires_at_ms": None},
        )
        with (
            patch(
                "laomedo.agents.agents.opencode.auth.utils.console_provider",
                return_value=credential,
            ) as auth,
            patch("laomedo.agents.agents.base.utils._json", side_effect=write),
            patch("laomedo.docker.DockerRuntime") as runtime,
            patch.object(
                sys,
                "argv",
                [
                    str(script),
                    "--implementation",
                    str(implementation),
                    "--provider",
                    "opencode",
                ],
            ),
            redirect_stdout(captured),
        ):
            if phase == "docker-open":
                runtime.return_value.client.side_effect = RuntimeError(expected)
            if phase == "sentinel-start":
                runtime.ensure_image.return_value = "sha256:" + "a" * 64
                runtime.start_session.side_effect = RuntimeError(expected)
            failed = False
            try:
                target.main()
            except (OSError, RuntimeError) as error:
                if str(error) != expected:
                    raise
                failed = True
            auth.assert_called_once()
        rows = [
            json.loads(line)
            for line in captured.getvalue().splitlines()
            if line.startswith("{")
        ]
        retained = next(
            row for row in rows if row["stage"] == "failed_private_state_retained"
        )
        root = Path(retained["directory"]).resolve()
        if root.parent != Path(
            tempfile.gettempdir()
        ).resolve() or not root.name.startswith("laomedo-codex-restart-"):
            raise RuntimeError("unexpected_control_cleanup_path")
        try:
            checks = {
                "stage": phase,
                "model_prompts": 0,
                "synthetic_auth_written_before_failure": bool(writes),
                "injected_failure_observed": failed,
                "private_profile_removed": not (root / "profile").exists(),
                "failure_directory_retained": root.exists(),
                "cleanup_reported": any(
                    row.get("stage") == "temporary_profile_cleanup"
                    and row.get("removed") is True
                    for row in rows
                ),
            }
            print(json.dumps(checks), flush=True)
            if not all(
                value
                for key, value in checks.items()
                if key not in {"stage", "model_prompts"}
            ):
                raise RuntimeError("early_setup_cleanup_not_confirmed")
        finally:
            shutil.rmtree(root)


if __name__ == "__main__":
    main()
