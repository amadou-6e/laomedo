"""Print only sandbox/approval fields for one private Codex turn context."""

import argparse
import json
from pathlib import Path


def inspect_turn_policy(home: Path, turn_id: str) -> dict:
    home = home.resolve(strict=True)
    for path in home.rglob("*.jsonl"):
        if (path.is_symlink() or getattr(path, "is_junction", lambda: False)()
                or not path.resolve().is_relative_to(home)):
            continue
        with path.open(encoding="utf-8", errors="replace") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                payload = record.get("payload") or {}
                if (record.get("type") != "turn_context" or
                        payload.get("turn_id") != turn_id):
                    continue
                policy = payload.get("sandbox_policy")
                return {
                    "found": True,
                    "sandbox_policy_type": (policy.get("type") if isinstance(policy, dict)
                                            else type(policy).__name__),
                    "approval_policy": payload.get("approval_policy"),
                    "context_field_names": sorted(key for key in payload
                                                  if key in ("sandbox_policy",
                                                             "approval_policy",
                                                             "model", "effort")),
                }
    return {"found": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-home", required=True, type=Path)
    parser.add_argument("--turn-id", required=True)
    args = parser.parse_args()
    home = args.codex_home.resolve(strict=True)
    if (home / "auth.json").is_symlink() or not (home / "auth.json").is_file():
        raise ValueError("private Codex home unavailable")
    print(json.dumps(inspect_turn_policy(home, args.turn_id), indent=2))


if __name__ == "__main__":
    main()
