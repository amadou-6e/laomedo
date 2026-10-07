"""Credential-free Codex app-server skill-discovery probe for issue #78."""

import argparse
import json
from pathlib import Path
import shutil
import sys
import tempfile


SHARED = Path(__file__).resolve().parents[1] / "feasibility" / "120"
sys.path.insert(0, str(SHARED))
from _shared import (AppServer, codex_version, compare_personal_roots,
                     construct_env, hash_path, hash_personal_roots)


NAME = "fixture-native-78"
BODY = ("---\nname: fixture-native-78\n"
        "description: Synthetic skill for a credential-free discovery check.\n"
        "---\n\nPrivate fixture body; no model turn reads this text.\n")


def run(codex: Path) -> dict:
    before = hash_personal_roots()
    real_home = Path.home().resolve()
    result = {"issue": 78, "model_turns": 0, "selection_mode": "native_listing_only"}
    with tempfile.TemporaryDirectory(prefix="laomedo-exp78-") as temporary:
        state = Path(temporary).resolve()
        private_home = state / "home"
        codex_home = state / "codex-home"
        source = state / "source" / NAME / "SKILL.md"
        effective = state / "project" / ".agents" / "skills" / NAME / "SKILL.md"
        for folder in (private_home, codex_home, source.parent, effective.parent,
                       state / "appdata", state / "localappdata"):
            folder.mkdir(parents=True, exist_ok=True)
        source.write_text(BODY, encoding="utf-8")
        shutil.copyfile(source, effective)
        result["source_sha256"] = hash_path(source)
        result["effective_before_sha256"] = hash_path(effective)
        result["effective_within_private_project"] = effective.resolve().is_relative_to(state)
        env = construct_env(private_home, codex_home, state, codex.parent)
        result["codex_version"] = codex_version(codex, env).splitlines()[0]
        server = None
        try:
            server = AppServer(codex, state / "project", env, state)
            initialized, detail = server.initialize()
            result["initialized"] = initialized
            if not initialized:
                result["error_category"] = "initialize_rejected"
                result["error_code"] = detail.get("code") if isinstance(detail, dict) else None
            else:
                listing = server.send("skills/list", {
                    "cwds": [str(state / "project")], "forceReload": True})
                if "result" not in listing:
                    result["error_category"] = "skills_list_rejected"
                    error = listing.get("error") or {}
                    result["error_code"] = error.get("code") if isinstance(error, dict) else None
                else:
                    batches = listing["result"].get("data") or []
                    skills = batches[0].get("skills") or [] if batches else []
                    matches = [item for item in skills if item.get("name") == NAME]
                    result["fixture_listing_count"] = len(matches)
                    result["listed_skill_count"] = len(skills)
                    paths = [Path(item.get("path", "")).resolve() for item in skills]
                    path_roots = {
                        "private_project": (state / "project").resolve(),
                        "private_profile": private_home.resolve(),
                        "private_codex_home": codex_home.resolve(),
                        "personal_agents_skills": (real_home / ".agents" / "skills").resolve(),
                        "personal_codex_skills": (real_home / ".codex" / "skills").resolve(),
                        "codex_installation": codex.parents[2].resolve(),
                    }
                    classes = {key: 0 for key in path_roots}
                    classes["other"] = 0
                    for path in paths:
                        group = next((key for key, root in path_roots.items()
                                      if path.is_relative_to(root)), "other")
                        classes[group] += 1
                    result["listed_path_classes"] = classes
                    result["listed_paths_under_real_home"] = sum(
                        path.is_relative_to(real_home) for path in paths)
                    result["fixture_path_matches_effective"] = (
                        len(matches) == 1 and
                        Path(matches[0].get("path", "")).resolve() == effective.resolve())
                    result["fixture_offered"] = (
                        len(matches) == 1 and result["fixture_path_matches_effective"])
                    result["native_listing_event"] = {
                        "method": "skills/list",
                        "request": {"cwd_class": "private_project", "forceReload": True},
                        "response": {
                            "skill_count": len(skills),
                            "fixture_name": NAME if len(matches) == 1 else None,
                            "fixture_path_class": "private_project"
                            if result["fixture_path_matches_effective"] else "other",
                        },
                    }
        except Exception as error:
            result["error_category"] = type(error).__name__
        finally:
            if server is not None:
                result["stderr_categories"] = server.close()
            result["effective_after_sha256"] = hash_path(effective)
            result["effective_unchanged"] = (
                result["source_sha256"] == result["effective_before_sha256"] ==
                result["effective_after_sha256"])
    result["personal_roots_unchanged"] = compare_personal_roots(
        before, hash_personal_roots())
    result["personal_session_comparison"] = (
        "unchanged" if result["personal_roots_unchanged"].get(".codex_sessions")
        else "changed_during_concurrent_ide_session_attribution_unknown")
    classes = result.get("listed_path_classes") or {}
    result["pass"] = (
        result.get("fixture_offered") is True and
        classes.get("personal_agents_skills") == 0 and
        classes.get("personal_codex_skills") == 0 and
        result["effective_unchanged"] and
        all(result["personal_roots_unchanged"].get(key) is True for key in
            (".agents_skills", ".codex_skills", ".codex_auth.json")))
    result["skill_body_read"] = "unknown"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex", required=True, type=Path)
    args = parser.parse_args()
    result = run(args.codex.resolve(strict=True))
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
