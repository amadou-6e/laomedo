"""Run the frozen, credential-free EXP-108 synthetic cases."""

import argparse
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

from connection import ConnectionBroker, ConnectionRefused
from fake_provider import FakeProvider


HERE = Path(__file__).resolve().parent


def _id(value):
    return sha256(value.encode("utf-8")).hexdigest()[:12]


def _refused(function, label):
    try:
        function()
    except ConnectionRefused:
        return {"case": label, "passed": True}
    raise AssertionError(f"unexpectedly accepted: {label}")


@contextmanager
def _ambient_credentials(folder):
    shim = Path(folder) / "gh"
    shim.write_text("fake gh shim must never run\n", encoding="utf-8", newline="\n")
    env = {"GH_TOKEN": "synthetic-ambient-should-not-use",
           "GITHUB_TOKEN": "synthetic-ambient-should-not-use",
           "GH_HOST": "fake.invalid", "GIT_CONFIG_COUNT": "1",
           "GIT_CONFIG_KEY_0": "credential.helper",
           "GIT_CONFIG_VALUE_0": "synthetic-helper",
           "PATH": str(folder) + os.pathsep + os.environ.get("PATH", "")}
    with patch.dict(os.environ, env), patch("subprocess.run", side_effect=AssertionError("ambient gh called")):
        yield


def run():
    cases = []
    with TemporaryDirectory(prefix="laomedo-exp108-") as folder, FakeProvider() as provider:
        db = Path(folder) / "broker.sqlite3"
        broker = ConnectionBroker(db, provider.url)
        provider.add_token("synthetic-app", token_type="app_user")
        provider.add_token("synthetic-fg")
        provider.add_token("synthetic-fg-next")
        provider.add_token("synthetic-other", account="bob")
        provider.add_token("synthetic-classic", token_type="classic")
        provider.add_token("synthetic-expired", expired=True)
        provider.add_token("synthetic-noscope", operations=("contents:read",))
        provider.add_token("synthetic-wrongrepo", repositories=("org/other",))

        with _ambient_credentials(folder):
            cases.append(_refused(lambda: broker.connect_token(
                owner="laomedo-alice", account="alice", repository="org/repo", token=""),
                "ambient_credentials_not_fallback"))
            pending = broker.begin_browser(owner="laomedo-alice", session="browser-1",
                                           account="alice", repository="org/repo")
            provider.add_code("synthetic-code", "synthetic-app", pending["state"])
            cases.append(_refused(lambda: broker.finish_browser(
                owner="laomedo-bob", session="browser-1", state=pending["state"],
                code="synthetic-code"), "callback_wrong_owner"))
            cases.append(_refused(lambda: broker.finish_browser(
                owner="laomedo-alice", session="browser-other", state=pending["state"],
                code="synthetic-code"), "callback_wrong_session"))
            cases.append(_refused(lambda: broker.finish_browser(
                owner="laomedo-alice", session="browser-1", state="wrong-state",
                code="synthetic-code"), "callback_wrong_state"))
            other_pending = broker.begin_browser(owner="laomedo-alice", session="browser-1",
                    account="alice", repository="org/repo")
            cases.append(_refused(lambda: broker.finish_browser(
                owner="laomedo-alice", session="browser-1", state=other_pending["state"],
                code="synthetic-code"), "code_for_other_valid_state_refused"))
            # Recreate the broker before callback to prove pending state is durable.
            broker = ConnectionBroker(db, provider.url)
            browser = broker.finish_browser(owner="laomedo-alice", session="browser-1",
                                            state=pending["state"], code="synthetic-code")
            assert browser["mode"] == "browser" and browser["generation"] == 1
            cases.append({"case": "browser_callback_after_broker_restart", "passed": True})
            cases.append(_refused(lambda: broker.finish_browser(
                owner="laomedo-alice", session="browser-1", state=pending["state"],
                code="synthetic-code"), "callback_replay"))
            browser_run = broker.issue_run(connection_id=browser["id"],
                    owner="laomedo-alice", repository="org/repo",
                    operations=("contents:write",))
            assert browser_run["capability"] and "token" not in browser_run
            assert broker.mediated_write(browser_run["capability"], "contents:write") == {"accepted": True}
            cases.append({"case": "browser_run_mediated", "passed": True})

            wrong = broker.begin_browser(owner="laomedo-alice", session="browser-2",
                                          account="alice", repository="org/repo")
            provider.add_code("synthetic-bad-code", "synthetic-other", wrong["state"])
            cases.append(_refused(lambda: broker.finish_browser(
                owner="laomedo-alice", session="browser-2", state=wrong["state"],
                code="synthetic-bad-code"), "browser_account_mismatch"))
            provider.add_token("synthetic-browser-wrongrepo", token_type="app_user",
                               repositories=("org/other",))
            wrong_repo = broker.begin_browser(owner="laomedo-alice", session="browser-3",
                    account="alice", repository="org/repo")
            provider.add_code("synthetic-browser-wrongrepo-code",
                              "synthetic-browser-wrongrepo", wrong_repo["state"])
            cases.append(_refused(lambda: broker.finish_browser(
                owner="laomedo-alice", session="browser-3", state=wrong_repo["state"],
                code="synthetic-browser-wrongrepo-code"), "browser_repository_mismatch"))

            token = broker.connect_token(owner="laomedo-alice", account="alice",
                                          repository="org/repo", token="synthetic-fg")
            token_run = broker.issue_run(connection_id=token["id"],
                    owner="laomedo-alice", repository="org/repo",
                    operations=("contents:write",))
            assert broker.mediated_write(token_run["capability"], "contents:write") == {"accepted": True}
            cases.append({"case": "explicit_token_run_mediated", "passed": True})
            cases.append(_refused(lambda: broker.connect_token(
                owner="laomedo-alice", account="alice", repository="org/repo",
                token="synthetic-classic"), "classic_token_refused"))
            cases.append(_refused(lambda: broker.connect_token(
                owner="laomedo-alice", account="alice", repository="org/repo",
                token="synthetic-expired"), "expired_token_refused"))
            cases.append(_refused(lambda: broker.connect_token(
                owner="laomedo-alice", account="alice", repository="org/repo",
                token="synthetic-noscope"), "missing_scope_refused"))
            cases.append(_refused(lambda: broker.connect_token(
                owner="laomedo-alice", account="alice", repository="org/repo",
                token="synthetic-wrongrepo"), "wrong_repository_refused"))
            cases.append(_refused(lambda: broker.connect_token(
                owner="laomedo-alice", account="alice", repository="org/repo",
                token="synthetic-other"), "wrong_account_refused"))
            cases.append(_refused(lambda: broker.issue_run(connection_id=token["id"],
                owner="laomedo-bob", repository="org/repo",
                operations=("contents:write",)), "cross_user_refused"))

            updated = broker.replace_token(connection_id=token["id"],
                    owner="laomedo-alice", token="synthetic-fg-next")
            assert updated["generation"] == 2
            cases.append(_refused(lambda: broker.mediated_write(
                token_run["capability"], "contents:write"), "old_generation_refused"))
            assert broker.mediated_write(browser_run["capability"], "contents:write") == {"accepted": True}
            cases.append({"case": "unrelated_browser_run_still_works", "passed": True})
            new_run = broker.issue_run(connection_id=token["id"],
                    owner="laomedo-alice", repository="org/repo",
                    operations=("contents:write",))
            broker.disconnect(token["id"], "laomedo-alice")
            cases.append(_refused(lambda: broker.mediated_write(
                new_run["capability"], "contents:write"), "disconnect_refuses_active_run"))
            cases.append(_refused(lambda: broker.issue_run(connection_id=token["id"],
                owner="laomedo-alice", repository="org/repo",
                operations=("contents:write",)), "disconnect_refuses_new_run"))
            broker = ConnectionBroker(db, provider.url)
            assert broker.describe(browser["id"], "laomedo-alice")["state"] == "ready"
            assert broker.mediated_write(browser_run["capability"], "contents:write") == {"accepted": True}
            cases.append({"case": "ready_connection_survives_broker_restart", "passed": True})
            provider.tokens.pop("synthetic-app")
            cases.append(_refused(lambda: broker.mediated_write(
                browser_run["capability"], "contents:write"), "provider_revocation_refused"))

            # The stage payload and provider journal cannot contain secrets.
            public = json.dumps({"browser": browser, "token": token,
                                 "run": browser_run, "journal": provider.requests})
            assert not any(secret in public for secret in provider.tokens)
            assert "synthetic-app" not in public and "synthetic-fg" not in public
            assert "synthetic-ambient-should-not-use" not in public
            cases.append({"case": "no_secret_in_stage_or_observation", "passed": True})

        return {"protocol": "EXP-108-v2", "synthetic_only": True,
                "model_turns": 0, "real_github_requests": 0,
                "browser_connection_id": _id(browser["id"]),
                "token_connection_id": _id(token["id"]),
                "token_generation_after_rotation": updated["generation"],
                "fake_provider_requests": len(provider.requests),
                "fake_provider_writes": sum(r["path"] == "/write" for r in provider.requests),
                "cases": cases}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--record", action="store_true",
                        help="write the one-time sanitized observation")
    args = parser.parse_args()
    observation = run()
    if args.record:
        output = HERE / "observation-v2.json"
        if output.exists():
            raise SystemExit("observation already exists; refusing to overwrite")
        output.write_text(json.dumps(observation, indent=2) + "\n",
                          encoding="utf-8", newline="\n")
    else:
        print(json.dumps({"passed": all(c["passed"] for c in observation["cases"]),
                          "cases": len(observation["cases"]),
                          "synthetic_only": True}))


if __name__ == "__main__":
    main()
