"""One-shot capture of synthetic literal-command comparison controls."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
IDENTITY = "exp100-cli-s9-20261009"


def run(private):
    if subprocess.run(["git", "status", "--porcelain"], cwd=ROOT,
                      check=True, capture_output=True).stdout.strip():
        raise ValueError("source_not_clean")
    private.mkdir(parents=True, exist_ok=True)
    with (private / (IDENTITY + ".claim")).open("x") as file:
        file.write(IDENTITY)
    command = ["node", "--test", "experiments/exp100/test_gh_adapter.mjs"]
    observed = subprocess.run(command, cwd=ROOT, capture_output=True, timeout=30)
    raw = observed.stdout
    with (private / (IDENTITY + ".tap")).open("xb") as file:
        file.write(raw)
    observation = {
        "identity": IDENTITY, "command": command,
        "source_sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
            capture_output=True, check=True).stdout.decode().strip(),
        "adapter_sha256": sha256((ROOT / "experiments/exp100/gh_adapter.mjs").read_bytes()).hexdigest(),
        "tests_sha256": sha256((ROOT / "experiments/exp100/test_gh_adapter.mjs").read_bytes()).hexdigest(),
        "tap_sha256": sha256(raw).hexdigest(), "exit_code": observed.returncode,
        "result": "passed" if (observed.returncode == 0 and b"# pass 11" in raw and b"# fail 0" in raw) else "failed",
        "scope": "injected synthetic command/request and refusal controls only",
        "declared_model_turns": 0, "declared_real_provider_calls": 0,
        "production_installed": False, "native_gh_parity": False,
    }
    with (private / (IDENTITY + ".json")).open("x", encoding="utf-8", newline="\n") as file:
        json.dump(observation, file, indent=2, sort_keys=True); file.write("\n")
    return observation


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--private-state", required=True, type=Path)
    print(json.dumps(run(parser.parse_args().private_state), sort_keys=True))
