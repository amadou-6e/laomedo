"""Compare public native catalog fields without printing private run contents."""

import json
import os
from pathlib import Path


def main():
    before = json.loads(
        Path(
            "C:/CodeWorkspace/laomedo/.tools/claude-skill-catalog-seed.json"
        ).read_text(encoding="utf-8-sig")
    )
    root = (
        Path(os.environ["LOCALAPPDATA"])
        / "Laomedo/acceptance/assistant-saved-293-01a1ba85/provider-runs"
    )
    path = max(root.rglob("record.json"), key=lambda item: item.stat().st_mtime)
    after = json.loads(path.read_text(encoding="utf-8"))
    current = after["native_commands"]
    old_rows = before["catalog"]["commands"]
    new_rows = current["catalog"]["commands"]
    print("status", after["status"], "error", after.get("error_category"))
    print("skill-list equal", before["skills"] == after.get("native_builtin_skills"))
    print("order equal", [r["name"] for r in old_rows] == [r["name"] for r in new_rows])
    old = {row["name"]: row for row in old_rows}
    new = {row["name"]: row for row in new_rows}
    print(
        "added",
        sorted(new.keys() - old.keys()),
        "removed",
        sorted(old.keys() - new.keys()),
    )
    for name in sorted(old.keys() & new.keys()):
        for key in old[name].keys() | new[name].keys():
            if old[name].get(key) != new[name].get(key):
                print(
                    "changed",
                    name,
                    key,
                    repr(old[name].get(key))[:160],
                    repr(new[name].get(key))[:160],
                )
    print("revision", before["revision"], current["projection"]["revision"])


if __name__ == "__main__":
    main()
