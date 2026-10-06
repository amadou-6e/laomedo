"""One-shot, zero-credential EXP-100 local probe."""

import argparse
import json
import os
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path


HERE = Path(__file__).parent
REPO = "example/disposable"
ALL = ["git_push", "git_fetch", "pr_create", "pr_list", "issue_create",
       "issue_list", "actions_read", "api_get", "api_post", "graphql_read",
       "graphql_mutation"]


def git(*args, cwd=None):
    result = subprocess.run(["git", *map(str, args)], cwd=cwd, capture_output=True, text=True, check=False)
    if result.returncode:
        raise AssertionError(f"git failed: {args}: {result.stderr}")
    return result.stdout.strip()


def call(port, grant, operation, effect_id=None, payload=None, repo=REPO):
    cmd = [sys.executable, str(HERE / "client.py"), "--url", f"http://127.0.0.1:{port}",
           "--grant", grant, "--repo", repo]
    if effect_id is not None:
        cmd += ["--effect-id", effect_id]
    cmd += [operation, "--payload", json.dumps(payload or {})]
    child_env = os.environ.copy()
    for name in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN", "GIT_ASKPASS"):
        child_env.pop(name, None)
    result = subprocess.run(cmd, capture_output=True, text=True, env=child_env, timeout=25, check=False)
    if not result.stdout:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


def expect(result, *, status=200, error=None, state=None):
    assert result["http_status"] == status, result
    if error is not None:
        assert result["error"] == error, result
    if state is not None:
        assert result["state"] == state, result
    return result


def run():
    observations = {}
    with tempfile.TemporaryDirectory(prefix="laomedo-exp100-") as tmp:
        base = Path(tmp)
        bare, work, db_path = base / "remote.git", base / "workspace", base / "broker.db"
        git("init", "--bare", bare)
        git("init", "-b", "main", work)
        git("-C", work, "config", "user.email", "probe@example.invalid")
        git("-C", work, "config", "user.name", "EXP-100 Probe")
        (work / "README.md").write_text("disposable probe\n", encoding="utf-8", newline="\n")
        git("-C", work, "add", "README.md")
        git("-C", work, "commit", "-m", "probe")
        git("-C", work, "remote", "add", "origin", bare)
        observations["local_git_commit"] = git("-C", work, "rev-parse", "HEAD")
        with closing(sqlite3.connect(db_path)) as db, db:
            db.executescript("""
                CREATE TABLE grants(id TEXT PRIMARY KEY, repo TEXT NOT NULL, workspace TEXT NOT NULL,
                    operations TEXT NOT NULL, expires_at REAL NOT NULL, revoked INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE effects(grant_id TEXT NOT NULL, id TEXT NOT NULL, hash TEXT NOT NULL,
                    state TEXT NOT NULL, result TEXT, PRIMARY KEY(grant_id,id));
                CREATE TABLE upstream_effects(id INTEGER PRIMARY KEY, operation TEXT NOT NULL, marker TEXT);
            """)
            for grant in ("run-a", "run-b"):
                db.execute("INSERT INTO grants VALUES (?,?,?,?,?,0)",
                           (grant, REPO, str(work), json.dumps(ALL), time.time() + 3600))
            db.execute("INSERT INTO grants VALUES (?,?,?,?,?,0)",
                       ("read-only", REPO, str(work), json.dumps(["pr_list"]), time.time() + 3600))
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        service_env = os.environ.copy()
        for name in ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN"):
            service_env.pop(name, None)
        service = subprocess.Popen([sys.executable, str(HERE / "broker.py"), "--db", str(db_path),
                                    "--port", str(port)], env=service_env,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        try:
            for _ in range(100):
                if service.poll() is not None:
                    raise AssertionError(f"broker exited: {service.stderr.read()}")
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.1):
                        break
                except OSError:
                    time.sleep(0.02)
            else:
                raise AssertionError("broker did not start")
            observations["git_push"] = expect(call(port, "run-a", "git_push", "push-1"))
            assert git("--git-dir", bare, "rev-parse", "refs/heads/probe") == observations["local_git_commit"]
            observations["git_fetch"] = expect(call(port, "run-a", "git_fetch"))
            for operation in ("pr_create", "issue_create", "api_post", "graphql_mutation"):
                observations[operation] = expect(call(port, "run-a", operation, operation + "-1",
                                                     {"marker": operation + "-marker"}))
            for operation in ("pr_list", "issue_list", "actions_read", "api_get", "graphql_read"):
                observations[operation] = expect(call(port, "run-a", operation))
            observations["wrong_repo"] = expect(call(port, "run-a", "pr_list", repo="wrong/repo"),
                                                status=403, error="repository_denied")
            observations["denied_operation"] = expect(call(port, "read-only", "pr_create", "denied-1"),
                                                       status=403, error="operation_denied")
            observations["secret_export"] = expect(call(port, "run-a", "auth_token"),
                                                   status=403, error="unsupported_operation")
            observations["unknown_grant"] = expect(call(port, "missing", "pr_list"),
                                                   status=403, error="grant_unavailable")
            observations["repeat_confirmed"] = expect(call(port, "run-a", "pr_create", "pr_create-1",
                                                           {"marker": "pr_create-marker"}))
            assert observations["repeat_confirmed"]["resent"] is False
            observations["changed_request"] = expect(call(port, "run-a", "pr_create", "pr_create-1",
                                                          {"marker": "changed"}),
                                                     status=409, error="effect_conflict")
            observations["lost_response"] = expect(call(port, "run-a", "issue_create", "lost-1",
                                                        {"marker": "lost-marker", "simulate_lost_response": True}),
                                                   status=202, state="unknown")
            observations["repeat_uncertain"] = expect(call(port, "run-a", "issue_create", "lost-1",
                                                           {"marker": "lost-marker", "simulate_lost_response": True}),
                                                      status=202, state="unknown")
            observations["same_id_other_run"] = expect(call(port, "run-b", "pr_create", "pr_create-1",
                                                           {"marker": "other-run-marker"}))
            with closing(sqlite3.connect(db_path)) as db, db:
                count = db.execute("SELECT count(*) FROM upstream_effects WHERE marker='lost-marker'").fetchone()[0]
                assert count == 1
                db.execute("UPDATE grants SET revoked=1 WHERE id='run-a'")
            start = time.monotonic()
            observations["revoked"] = expect(call(port, "run-a", "pr_list"), status=403,
                                             error="grant_unavailable")
            observations["revocation_seconds"] = round(time.monotonic() - start, 3)
            assert observations["revocation_seconds"] < 60
            observations["other_run"] = expect(call(port, "run-b", "pr_list"))
            with closing(sqlite3.connect(db_path)) as db, db:
                db.execute("UPDATE grants SET expires_at=0 WHERE id='run-b'")
            observations["expired"] = expect(call(port, "run-b", "pr_list"), status=403,
                                             error="grant_unavailable")
            with closing(sqlite3.connect(db_path)) as db, db:
                observations["upstream_effect_counts"] = dict(db.execute(
                    "SELECT operation,count(*) FROM upstream_effects GROUP BY operation"))
            assert observations["upstream_effect_counts"]["pr_create"] == 2
            assert observations["upstream_effect_counts"]["issue_create"] == 2
            observations["host_token_vars_suppressed_from_child"] = sorted(
                name for name in child_env_names() if name in os.environ)
            # The client subprocess is launched with these variables removed;
            # this does not audit container mounts or other local processes.
            observations["agent_token_vars_removed"] = True
            observations["model_turns"] = 0
        finally:
            service.terminate()
            try:
                service.wait(timeout=5)
            except subprocess.TimeoutExpired:
                service.kill()
                service.wait(timeout=5)
    return observations


def child_env_names():
    return ("GH_TOKEN", "GITHUB_TOKEN", "GH_ENTERPRISE_TOKEN", "GITHUB_ENTERPRISE_TOKEN", "GIT_ASKPASS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", action="store_true")
    args = parser.parse_args()
    result = run()
    if args.record:
        destination = HERE / "observation.json"
        if destination.exists():
            raise SystemExit("observation already exists; refusing to overwrite")
        destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=2, sort_keys=True))
