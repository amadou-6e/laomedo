"""Internal compatibility controls; no live OAuth, Docker or agent acceptance."""

import hashlib
import json
from contextlib import closing, redirect_stdout
from datetime import datetime, timedelta, timezone
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from pydantic import ValidationError

from laomedo.agents.activity.models import ActivityAttemptRecord
from laomedo.agents.agents.claude.activity.models import ClaudeTelemetryEnvironment
from laomedo.agents.agents.opencode.activity.models import OpenCodeTokenUsage
from laomedo.agents.agents.opencode.models import OpenCodeRuntimeIdentity
from laomedo.host.credentials.siwc.connection import ChatGPTConnection
from laomedo.host.credentials.siwc.models import (
    OAuthAccount,
    OAuthAttempt,
    OAuthAuthorizationRequest,
    OAuthCodeExchange,
)
from laomedo.host.credentials.siwc.settings import AUTH_ORIGIN, RESOURCE, SCOPES
from laomedo.host.leases.grants import GrantBook
from laomedo.host.leases.models import (
    ContainerIdentity,
    GrantWindow,
    LeaseClock,
    LeaseGrant,
    LeaseRevocationRecord,
)
from laomedo.host.mediation.models import AuthorizedLeaseScope, MediationServiceRecord
from laomedo.host.publication.bundle.models import (
    BundleVerificationRecord,
    ContainerStageRecord,
)
from laomedo.host.publication.handoff.models import PullRequestPublicationRequest
from laomedo.host.publication.verified.models import (
    VerifiedStage,
    VerifiedStageIdentity,
)
from laomedo.work_graph.github import import_pages
from laomedo.work_graph.launch import preflight
from laomedo.github.models import GitHubGrantBinding, GitHubOperationIntent


class StructuredHostRecordsTests(unittest.TestCase):
    """Pin old construction boundaries independently of their new serializers."""

    def test_unconnected_approval_round_trip_preserves_optional_base_and_null_connection(
        self,
    ):
        from laomedo.host.mediation.authority import RunGrantAuthority

        for operations in ({"actions_read"}, {"git_fetch"}, {"pr_update"}):
            with self.subTest(operations=operations), TemporaryDirectory() as temporary:
                authority = RunGrantAuthority(Path(temporary) / "authority.sqlite")
                targets = {17: "develop"}
                reference = authority.approve(
                    invocation_id="invocation",
                    repository="owner/repo",
                    branch="work",
                    operations=operations,
                    reviewed_by="reviewer",
                    target_prs=targets,
                    base_branch="develop",
                )
                request = authority.bind_run(reference, "run")
                expected = dict(
                    invocation_id="invocation", repository="owner/repo", branch="work"
                )
                if operations != {"actions_read"}:
                    expected["base_branch"] = "develop"
                self.assertEqual(request, expected)
                lease = {"run_id": "run", "token": "private-lease"}
                scope = authority.authorize_lease(lease, request)
                self.assertEqual(
                    scope,
                    {
                        **expected,
                        "operations": operations,
                        "approval_identity": "reviewer",
                        "connection_id": None,
                        "connection_generation": None,
                        "target_prs": targets,
                    },
                )
                self.assertIn("connection_id", scope)
                self.assertIn("connection_generation", scope)
                self.assertIsNone(scope["connection_id"])
                self.assertIsNone(scope["connection_generation"])
                self.assertIs(type(scope["operations"]), set)
                self.assertIs(type(next(iter(scope["target_prs"]))), int)
                self.assertEqual(authority.authorize_lease(lease, request), scope)
                self.assertIsNone(
                    authority.authorize_lease(
                        {**lease, "token": "other-lease"}, request
                    )
                )
                self.assertIsNone(
                    authority.authorize_lease(
                        lease, {**request, "base_branch": "other"}
                    )
                )

    def test_claude_attempt_preserves_original_serialized_field_order(self):
        # Captured order of the original Claude attempt writer; the shared
        # default serializer has a different order for the other providers.
        expected = dict(
            id="attempt",
            native_start=2,
            otel_start=3,
            usage_baseline={"thread": {"native_extension": None}},
            native_end=None,
            fresh_thread=False,
            otel_end=None,
            status="running",
            ended_at=None,
        )
        record = ActivityAttemptRecord(**expected).to_claude_record()
        self.assertEqual(record, expected)
        self.assertEqual(
            list(record),
            [
                "id",
                "native_start",
                "otel_start",
                "usage_baseline",
                "native_end",
                "fresh_thread",
                "otel_end",
                "status",
                "ended_at",
            ],
        )
        self.assertEqual(json.dumps(record), json.dumps(expected))

    def test_gateway_intent_hashes_preserve_request_identity_and_optional_changes(self):
        from test_live_github_issue import LiveGitHubIssueTests
        from test_live_github_pr import LiveGitHubPRTests

        for kind, case_type in (
            ("issue", LiveGitHubIssueTests),
            ("pr", LiveGitHubPRTests),
        ):
            for action in ("modify", "close"):
                with self.subTest(kind=kind, action=action):
                    case = case_type()
                    case.setUp()
                    try:
                        operation = dict(
                            action=action, request_id="request_a", grant_ref="grant"
                        )
                        if action == "modify":
                            operation["changes"] = {"title": "Revue é", "body": ""}
                        case.gateway.execute(
                            case.url, ["research", "backend"], "open", 1, operation
                        )
                        with closing(case.store._connect()) as db:
                            authenticated = db.execute(
                                "SELECT grant_id,run_id FROM grants"
                            ).fetchone()
                            row = db.execute(
                                f"SELECT input_hash FROM {kind}_node_intents WHERE grant_ref=? AND request_id=?",
                                ("grant", "request_a"),
                            ).fetchone()
                        # This literal matches the a9317f6 gateway preimage.
                        expected = dict(
                            repository="owner/repo",
                            number=1,
                            labels=["backend", "research"],
                            state="open",
                            operation=operation,
                            binding={
                                "grant_id": authenticated["grant_id"],
                                "run_id": authenticated["run_id"],
                            },
                        )
                        preimage = json.dumps(
                            expected,
                            sort_keys=True,
                            separators=(",", ":"),
                            ensure_ascii=False,
                        )
                        self.assertEqual(
                            row["input_hash"],
                            "sha256:" + hashlib.sha256(preimage.encode()).hexdigest(),
                        )
                        model = GitHubOperationIntent(
                            **{
                                **expected,
                                "binding": GitHubGrantBinding(**expected["binding"]),
                            }
                        )
                        self.assertEqual(model.to_payload(), expected)
                        self.assertEqual(
                            set(model.to_payload()["operation"]),
                            (
                                {"action", "request_id", "grant_ref", "changes"}
                                if action == "modify"
                                else {"action", "request_id", "grant_ref"}
                            ),
                        )
                    finally:
                        case.doCleanups()

    def test_feedback_snapshot_keeps_original_labels_extensions_and_deadlines(self):
        from test_live_github_pr import LiveGitHubPRTests

        case = LiveGitHubPRTests()
        case.setUp()
        try:
            original = case.transport

            def extended_transport(repository, operation, payload):
                value = original(repository, operation, payload)
                return (
                    {
                        **value,
                        "provider_extension": {
                            "nullable": None,
                            "checks": ["é", False],
                        },
                    }
                    if operation == "pr_node_read"
                    else value
                )

            case.gateway.transports["owner/repo"] = extended_transport
            case.gateway.feedback_grants = {"owner/repo#1": "grant"}
            labels = ["research", "backend"]
            selected = case.gateway.execute(case.url, labels, "open", 1)
            issued = case.store.monotonic()
            with patch.object(case.store, "monotonic", return_value=issued):
                ticket = case.gateway.prepare_feedback(
                    case.url, labels, "open", 1, selected["content_digest"]
                )["ticket"]
            with closing(case.store._connect()) as db:
                row = db.execute(
                    "SELECT * FROM pr_feedback_tickets WHERE ticket=?", (ticket,)
                ).fetchone()
            expected = dict(
                repository_url=case.url,
                labels=labels,
                state="open",
                pr_number=1,
                expected=selected["content_digest"],
                pr=selected["pr"],
                issued_monotonic=issued,
                expires_monotonic=issued + 300,
            )
            self.assertEqual(json.loads(row["context"]), expected)
            self.assertEqual(list(json.loads(row["context"])), list(expected))
            self.assertEqual(row["expires"], 400)
            self.assertEqual(row["grant_ref"], "grant")
            self.assertTrue(row["request_id"].startswith("pr-feedback-"))
            for wall, monotonic in (
                (100, issued - 1),
                (100, issued + 300),
                (400, issued + 1),
            ):
                with (
                    self.subTest(wall=wall, monotonic=monotonic),
                    patch.object(case.store, "now", return_value=wall),
                    patch.object(case.store, "monotonic", return_value=monotonic),
                ):
                    with self.assertRaisesRegex(
                        ValueError, "^pr_feedback_ticket_invalid$"
                    ):
                        case.gateway.apply_feedback(ticket, {"action": "close"})
            self.assertEqual(case.fake.writes, [])
        finally:
            case.doCleanups()

    def test_work_grant_cli_flat_shape_and_redeemed_payload_match_old_writers(self):
        from laomedo.work_graph.__main__ import main
        from laomedo.work_graph.grants import LocalGrantAuthority
        from laomedo.work_graph.runs.errors import LaunchError
        from test_work_graph_launch import WorkGraphLaunchTests, WORK

        case = WorkGraphLaunchTests()
        case.setUp()
        try:
            with TemporaryDirectory() as temporary:
                snapshot = case.frozen.save(Path(temporary) / "snapshots")
                path = Path(temporary) / "grants.sqlite"
                output = StringIO()
                args = [
                    "issue-grant",
                    str(snapshot),
                    "--work-key",
                    WORK,
                    "--grant-store",
                    str(path),
                    "--timeout-seconds",
                    "30",
                    "--max-turns",
                    "0",
                ]
                with (
                    patch("sys.stdin") as stdin,
                    patch("builtins.input", return_value=WORK),
                    redirect_stdout(output),
                ):
                    stdin.isatty.return_value = True
                    self.assertEqual(main(args), 0)
                receipt = json.loads(output.getvalue())
                self.assertEqual(
                    set(receipt),
                    {
                        "grant_ref",
                        "work_key",
                        "graph_snapshot_id",
                        "content_digest",
                        "expires_at",
                        "timeout_seconds",
                        "max_turns",
                    },
                )
                self.assertEqual(
                    (
                        receipt["work_key"],
                        receipt["timeout_seconds"],
                        receipt["max_turns"],
                    ),
                    (WORK, 30, 0),
                )
                authority = LocalGrantAuthority(path)
                binding = preflight(case.frozen, case.frozen, WORK)
                redeemed = authority(receipt["grant_ref"], binding)
                self.assertEqual(
                    redeemed,
                    dict(
                        grant_id=receipt["grant_ref"],
                        operator_authorized=True,
                        work_key=WORK,
                        graph_snapshot_id=receipt["graph_snapshot_id"],
                        content_digest=receipt["content_digest"],
                        runner="langflow-local",
                        scope="stage-launch",
                        expires_at=receipt["expires_at"],
                        limits={"timeout_seconds": 30, "max_turns": 0},
                    ),
                )
                self.assertNotIn("operator_id", redeemed)
                with self.assertRaisesRegex(LaunchError, "^grant_invalid$"):
                    authority(receipt["grant_ref"], binding)
                ref = authority.issue(
                    work_key=WORK,
                    graph_snapshot=case.frozen,
                    expires_at=(
                        datetime.now(timezone.utc) + timedelta(minutes=5)
                    ).isoformat(),
                    timeout_seconds=30,
                    max_turns=0,
                )
                with closing(authority._connect()) as db, db:
                    db.execute(
                        "UPDATE grants SET expires_at=? WHERE grant_id=?",
                        ("2000-01-01T00:00:00+00:00", ref),
                    )
                with self.assertRaisesRegex(LaunchError, "^grant_expired$"):
                    authority(ref, binding)
                with closing(authority._connect()) as db:
                    self.assertIsNone(
                        db.execute(
                            "SELECT redeemed_at FROM grants WHERE grant_id=?", (ref,)
                        ).fetchone()[0]
                    )
        finally:
            case.doCleanups()

    def test_work_launch_summary_preserves_unknown_completion_without_output_leak(self):
        from unittest.mock import Mock
        from laomedo.work_graph.local_launch import launch_local_saved_flow

        record = dict(
            run_id="run",
            trace_id="trace",
            status="external_outcome_unknown",
            completion_basis=None,
            evidence_complete=0,
            dispatch_attempts=1,
            graph_revision="sha256:graph",
        )
        with TemporaryDirectory() as temporary:
            root = Path(temporary)
            snapshot = root / "snapshot.json"
            snapshot.write_text("{}", encoding="utf-8")
            for output in ("private-output", "", None):
                with (
                    self.subTest(output_present=bool(output)),
                    patch(
                        "laomedo.work_graph.models.GraphSnapshot.from_dict",
                        return_value=object(),
                    ),
                    patch(
                        "laomedo.work_graph.local_launch.LocalGrantAuthority",
                        return_value=Mock(path=root / "grants.sqlite"),
                    ),
                    patch(
                        "laomedo.work_graph.local_launch._private_path",
                        return_value=root / "runs.sqlite",
                    ),
                    patch("laomedo.work_graph.local_launch.WorkflowRunStore"),
                    patch("laomedo.work_graph.client.LangflowLocalClient"),
                    patch(
                        "laomedo.work_graph.local_launch.launch_github_docker_saved_flow_stage",
                        return_value=(record, output),
                    ),
                ):
                    summary = launch_local_saved_flow(
                        snapshot_path=snapshot,
                        work_key="github:S-20",
                        flow_id="flow",
                        langflow_base="http://127.0.0.1:8000",
                        grant_store=root / "grants.sqlite",
                        grant_ref="grant",
                        run_store=root / "runs.sqlite",
                        task="task",
                    )
                self.assertEqual(
                    summary,
                    {
                        **record,
                        "evidence_complete": False,
                        "output_present": bool(output),
                    },
                )
                self.assertEqual(
                    list(summary),
                    [
                        "run_id",
                        "trace_id",
                        "status",
                        "completion_basis",
                        "evidence_complete",
                        "dispatch_attempts",
                        "output_present",
                        "graph_revision",
                    ],
                )
                self.assertNotIn("private-output", json.dumps(summary))

    def assert_secret_output_excluded(self, model, secrets):
        for rendered in (
            repr(model),
            str(model),
            str(model.model_dump()),
            model.model_dump_json(),
        ):
            for secret in secrets:
                self.assertNotIn(secret, rendered)

    def test_oauth_authorization_query_preserves_order_and_optional_hints(self):
        base = dict(
            client_id="oaiapp_client",
            ext_agent_host_id="urn:uuid:host",
            redirect_uri="http://127.0.0.1:9000/auth/callback",
            scope="scope a",
            resource="https://resource.example",
            state="private-state",
            nonce="private-nonce",
            code_challenge="challenge",
        )
        for hints in (
            {},
            {"agent_name_hint": "Laomedo"},
            {"id_token_hint": "private-id-token", "login_hint": "private-email"},
            {
                "id_token_hint": {"legacy": "private-id-token"},
                "login_hint": ["private-email"],
            },
        ):
            with self.subTest(hints=list(hints)):
                request = OAuthAuthorizationRequest(**base, **hints)
                expected = dict(
                    client_id=base["client_id"],
                    ext_agent_host_id=base["ext_agent_host_id"],
                    response_type="code",
                    redirect_uri=base["redirect_uri"],
                    scope=base["scope"],
                    resource=base["resource"],
                    state=base["state"],
                    nonce=base["nonce"],
                    code_challenge_method="S256",
                    code_challenge=base["code_challenge"],
                    **hints,
                )
                self.assertEqual(request.to_query(), urlencode(expected))
                self.assert_secret_output_excluded(
                    request,
                    (
                        "private-state",
                        "private-nonce",
                        "private-id-token",
                        "private-email",
                    ),
                )

    def test_begin_preserves_private_attempt_and_legacy_account_hints(self):
        # Bypass filesystem/account enrollment; only this existing writer is tested.
        connection = object.__new__(ChatGPTConnection)
        connection.host_id = "urn:uuid:host"
        redirect = "http://127.0.0.1:9000/auth/callback"
        for account in (
            None,
            {
                "subject": "private-subject",
                "email": ["private-email"],
                "id_token": {"old": "private-token"},
            },
        ):
            client = None if account is None else "oaiapp_client"
            with (
                self.subTest(existing=account is not None),
                patch.object(connection, "_account", return_value=account),
                patch(
                    "laomedo.host.credentials.siwc.connection.secrets.token_urlsafe",
                    side_effect=["verifier", "state", "nonce"],
                ),
            ):
                attempt = connection.begin(redirect, client_id=client)
            self.assertEqual(
                list(attempt),
                [
                    "url",
                    "state",
                    "nonce",
                    "verifier",
                    "redirect_uri",
                    "client_id",
                    "previous_subject",
                ],
            )
            self.assertEqual(
                {key: value for key, value in attempt.items() if key != "url"},
                dict(
                    state="state",
                    nonce="nonce",
                    verifier="verifier",
                    redirect_uri=redirect,
                    client_id=client,
                    previous_subject=account["subject"] if account else None,
                ),
            )
            self.assertTrue(
                attempt["url"].startswith(AUTH_ORIGIN + "/api/accounts/authorize?")
            )
            self.assertIn(
                urlencode({"scope": SCOPES, "resource": RESOURCE}), attempt["url"]
            )
            self.assertIn(
                "id_token_hint=" if account else "agent_name_hint=Laomedo",
                attempt["url"],
            )

    def test_oauth_private_projections_and_safe_exception_text(self):
        attempt_values = dict(
            url="private-url",
            state="private-state",
            nonce="private-nonce",
            verifier="private-verifier",
            redirect_uri="http://callback",
            client_id=None,
            previous_subject=None,
        )
        attempt = OAuthAttempt(**attempt_values)
        self.assertEqual(attempt.to_private_payload(), attempt_values)
        self.assert_secret_output_excluded(
            attempt,
            tuple(
                value
                for key, value in attempt_values.items()
                if key in {"url", "state", "nonce", "verifier"}
            ),
        )
        exchange = OAuthCodeExchange(
            client_id="client",
            code="private-code",
            code_verifier="private-verifier",
            redirect_uri="http://callback",
            resource="resource",
        )
        self.assertEqual(
            exchange.to_private_payload(),
            dict(
                grant_type="authorization_code",
                client_id="client",
                code="private-code",
                code_verifier="private-verifier",
                redirect_uri="http://callback",
                resource="resource",
            ),
        )
        self.assert_secret_output_excluded(
            exchange, ("private-code", "private-verifier")
        )
        values = dict(
            client_id="client",
            subject="private-subject",
            issuer="issuer",
            email={"legacy": "private-email"},
            ext_agent_host_id="host",
            id_token="private-id",
            access_token="private-access",
            refresh_token="private-refresh",
            scopes=["a", "b"],
            expires_at=300,
            generation=2.5,
            state="active",
        )
        account = OAuthAccount(**values)
        self.assertEqual(account.to_private_record(), values)
        self.assertEqual(list(account.to_private_record()), list(values))
        self.assertIs(type(account.to_private_record()["expires_at"]), int)
        self.assert_secret_output_excluded(
            account,
            (
                "private-subject",
                "private-email",
                "private-id",
                "private-access",
                "private-refresh",
            ),
        )
        with self.assertRaises(ValidationError) as raised:
            OAuthAccount(**{**values, "access_token": ["private-invalid-access"]})
        # Pydantic's errors()/json() include inputs by default. Only explicit safe
        # projections and exception text are appropriate for diagnostics.
        for rendered in (
            str(raised.exception),
            repr(raised.exception),
            str(raised.exception.errors(include_input=False)),
            raised.exception.json(include_input=False),
        ):
            self.assertNotIn("private-invalid-access", rendered)

    def test_container_identity_only_unwraps_in_private_registration(self):
        identity = ContainerIdentity(
            name="container", run_id="run", token="private-lease"
        )
        self.assert_secret_output_excluded(identity, ("private-lease",))
        expected = dict(
            name="container",
            run_id="run",
            token="private-lease",
            runner_pid=123,
            created_at=4,
            mediation=None,
        )
        self.assertEqual(
            identity.registration(runner_pid=123, created_at=4, mediation=None),
            expected,
        )
        self.assertNotIn("docker_endpoint", expected)
        restored = ContainerIdentity.from_registration(expected)
        self.assertIsNone(restored.docker_endpoint)

    def test_lease_window_expiry_rollback_renewal_and_revocation(self):
        window = GrantWindow(
            clock=LeaseClock(wall=100, monotonic=10),
            wall_deadline=120,
            monotonic_deadline=30,
        )
        grant = LeaseGrant.from_window("grant", "private-lease", window)
        self.assertEqual(
            (grant.expires_at, grant.issued_monotonic, grant.expires_monotonic),
            (120, 10, 30),
        )
        self.assert_secret_output_excluded(grant, ("private-lease",))
        self.assertTrue(grant.bound_to("private-lease"))
        self.assertFalse(grant.bound_to("other"))
        for wall, monotonic, accepted in (
            (119, 29, True),
            (120, 29, False),
            (119, 30, False),
            (90, 9, False),
            (90, 10, True),
        ):
            with self.subTest(wall=wall, monotonic=monotonic):
                self.assertEqual(
                    grant.accepts(LeaseClock(wall=wall, monotonic=monotonic)), accepted
                )
        grant.renew(
            GrantWindow(
                clock=LeaseClock(wall=110, monotonic=20),
                wall_deadline=200,
                monotonic_deadline=200,
            )
        )
        self.assertEqual(
            (grant.expires_at, grant.issued_monotonic, grant.expires_monotonic),
            (160, 10, 70),
        )
        grant.revoke(115)
        self.assertFalse(grant.accepts(LeaseClock(wall=116, monotonic=21)))

    def test_grant_book_scope_renewal_and_denial_audit_match_old_rules(self):
        with TemporaryDirectory() as temporary:
            events = Path(temporary) / "events.jsonl"
            book = GrantBook(events)
            with (
                patch(
                    "laomedo.host.leases.grants.secrets.token_hex",
                    side_effect=["private-grant", "safe-id"],
                ),
                patch("laomedo.host.leases.grants.time.monotonic", return_value=10),
            ):
                grant_id, secret = book.issue("private-lease", 100, 200, 200)
            self.assertEqual((grant_id, secret), ("grant-safe-id", "private-grant"))
            grant = book.by_digest[hashlib.sha256(secret.encode()).hexdigest()]
            with patch("laomedo.host.leases.grants.time.monotonic", return_value=20):
                book.renew("other-parent", 110, 200, 200)
                self.assertEqual((grant.expires_at, grant.expires_monotonic), (150, 60))
                book.renew("private-lease", 110, 200, 200)
                self.assertEqual((grant.expires_at, grant.expires_monotonic), (160, 70))
            for wall, monotonic, accepted in (
                (120, 30, True),
                (90, 9, False),
                (160, 30, False),
                (120, 70, False),
            ):
                with (
                    patch("laomedo.host.leases.grants.time.time", return_value=wall),
                    patch(
                        "laomedo.host.leases.grants.time.monotonic",
                        return_value=monotonic,
                    ),
                ):
                    self.assertEqual(book.check(secret), (accepted, grant_id))
            # Expired grants cannot be revived through book renewal.
            with patch("laomedo.host.leases.grants.time.monotonic", return_value=70):
                book.renew("private-lease", 150, 300, 300)
            self.assertEqual((grant.expires_at, grant.expires_monotonic), (160, 70))
            self.assertEqual(book.revoke("other-parent", 120), [])
            self.assertEqual(book.revoke("private-lease", 120), [grant_id])
            self.assertEqual(book.revoke("private-lease", 121), [])
            with (
                patch("laomedo.host.leases.grants.time.time", return_value=121),
                patch("laomedo.host.leases.grants.time.monotonic", return_value=31),
            ):
                self.assertEqual(book.check(secret), (False, grant_id))
                self.assertEqual(book.check("unknown"), (False, None))
            observations = [
                json.loads(line)
                for line in events.read_text(encoding="utf-8").splitlines()
            ]
            self.assertEqual(
                observations[-1], dict(at=121, grant_id=None, accepted=False)
            )
            for secret_value in ("private-lease", "private-grant"):
                self.assertNotIn(secret_value, events.read_text(encoding="utf-8"))

    def test_revocation_preserves_omitted_and_explicit_null_evidence(self):
        values = dict(
            reason="lost",
            revoked_grants=["grant"],
            detected_at=1,
            revoked_at=2,
            detected_at_monotonic=10,
            revoked_at_monotonic=11,
        )
        self.assertEqual(LeaseRevocationRecord(**values).to_record(), values)
        complete = {
            **values,
            "cleanup_finished_at": None,
            "cleanup_finished_at_monotonic": None,
            "cleanup_verified": False,
            "state": {"observed": "unknown"},
        }
        self.assertEqual(LeaseRevocationRecord(**complete).to_record(), complete)

    def test_native_attempt_shape_preserves_provider_optional_freshness(self):
        values = dict(
            id="attempt",
            native_start=2,
            otel_start=3,
            native_end=None,
            otel_end=None,
            usage_baseline={"thread": {"native_extension": None}},
            status="running",
            ended_at=None,
        )
        self.assertEqual(ActivityAttemptRecord(**values).to_record(), values)
        self.assertEqual(
            ActivityAttemptRecord(**values, fresh_thread=False).to_record(),
            {**values, "fresh_thread": False},
        )

    def test_claude_telemetry_preserves_exact_privacy_environment(self):
        model = ClaudeTelemetryEnvironment(
            endpoint="http://127.0.0.1:8000", token="private-otel"
        )
        self.assert_secret_output_excluded(model, ("private-otel",))
        self.assertEqual(
            model.to_environment(),
            {
                "CLAUDE_CODE_ENABLE_TELEMETRY": "1",
                "CLAUDE_CODE_ENHANCED_TELEMETRY_BETA": "1",
                "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
                "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:8000",
                "OTEL_EXPORTER_OTLP_HEADERS": "Authorization=Bearer private-otel",
                "OTEL_METRICS_EXPORTER": "otlp",
                "OTEL_LOGS_EXPORTER": "otlp",
                "OTEL_TRACES_EXPORTER": "otlp",
                "OTEL_METRIC_EXPORT_INTERVAL": "1000",
                "OTEL_LOGS_EXPORT_INTERVAL": "1000",
                "OTEL_TRACES_EXPORT_INTERVAL": "1000",
                "OTEL_LOG_USER_PROMPTS": "0",
                "OTEL_LOG_ASSISTANT_RESPONSES": "0",
                "OTEL_LOG_TOOL_DETAILS": "0",
                "OTEL_LOG_TOOL_CONTENT": "0",
                "OTEL_METRICS_INCLUDE_ACCOUNT_UUID": "false",
            },
        )

    def test_opencode_usage_preserves_cache_and_reasoning_convention(self):
        usage = OpenCodeTokenUsage(
            non_cached_input=11,
            non_reasoning_output=13,
            reasoning=5,
            cache_read=7,
            cache_write=3,
        )
        self.assertEqual(
            usage.to_activity_usage().to_payload(),
            dict(
                inputTokens=21,
                cachedInputTokens=7,
                cacheWriteInputTokens=3,
                outputTokens=18,
                reasoningOutputTokens=5,
                totalTokens=39,
            ),
        )
        values = dict(
            runtime_version="native-version",
            image="controller",
            image_id=None,
            profile_id={"old": True},
            worker_image="worker",
            worker_image_id="sha256:worker",
            credential_binding="keyed-fingerprint",
        )
        self.assertEqual(
            OpenCodeRuntimeIdentity(**values).to_payload(),
            {"provider": "opencode", **values},
        )

    def test_mediation_metadata_preserves_omission_and_python_authority_types(self):
        values = dict(
            pid=12,
            port=8000,
            instance="instance",
            started_at=10,
            connection_id="connection",
            generation=2,
            repository="owner/repo",
        )
        self.assertEqual(MediationServiceRecord(**values).to_record(), values)
        self.assertEqual(
            MediationServiceRecord(**values, module_root=None).to_record(),
            {**values, "module_root": None},
        )
        scope = dict(
            invocation_id="invocation",
            repository="owner/repo",
            branch=None,
            operations={"pr_read"},
            approval_identity="approval",
            connection_id="connection",
            connection_generation=2,
            target_prs={3: "develop"},
        )
        result = AuthorizedLeaseScope(**scope).to_record()
        self.assertEqual(result, scope)
        self.assertIs(type(result["operations"]), set)
        self.assertIs(type(next(iter(result["target_prs"]))), int)

    def test_work_launch_preimages_match_captured_old_writer(self):
        repo = Path(__file__).resolve().parents[1]
        corpus = json.loads(
            (repo / "experiments/exp16/corpus.json").read_text(encoding="utf-8")
        )
        graph = import_pages(
            "verify/exp16", corpus["base"], fetched_at="2026-10-05T10:00:00+00:00"
        )
        expected = json.loads(
            (Path(__file__).parent / "contracts/work-launch-a9317f6.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(preflight(graph, graph, "github:S-20"), expected)

    def test_verified_stage_active_and_frozen_hash_preimages_match_old_writer(self):
        cases = json.loads(
            (Path(__file__).parent / "contracts/verified-stage-a9317f6.json").read_text(
                encoding="utf-8"
            )
        )
        for case in cases:
            with self.subTest(
                binding=(
                    "active" if "run_binding_sha256" in case["payload"] else "frozen"
                )
            ):
                identity = VerifiedStageIdentity(**case["payload"])
                self.assertEqual(identity.to_payload(), case["payload"])
                self.assertEqual(
                    json.dumps(
                        identity.to_payload(), sort_keys=True, separators=(",", ":")
                    ),
                    case["preimage"],
                )
                self.assertEqual(identity.digest(), case["digest"])
                stage = VerifiedStage.from_identity(identity, b"bundle")
                self.assertEqual(stage.stage_digest, case["digest"])
                self.assertEqual(
                    stage.bundle_sha256, case["payload"]["verified_bundle_sha256"]
                )
                self.assertEqual(stage.bundle, b"bundle")

    def test_initial_publication_records_do_not_invent_success(self):
        self.assertEqual(
            ContainerStageRecord().to_record(),
            dict(
                status="unknown",
                exit_code=None,
                cleanup_verified=False,
                output_sha256=None,
                output_bytes=None,
                stage_markers=[],
                success_marker_seen=False,
                export_class=None,
            ),
        )
        values = dict(
            run_id="run",
            attempt_id="attempt",
            source_bundle_sha256="source",
            baseline_bundle_sha256="base-bytes",
            baseline="base",
            commit="candidate",
            image_id="image",
        )
        record = BundleVerificationRecord(**values).to_record()
        self.assertEqual(
            record, {**values, "status": "unknown", "policy_approved": False}
        )
        # The service still owns mutable outcome/finally downgrades after projection.
        record.update(status="success", policy_approved=True)
        record["status"] = "cleanup_unknown"
        self.assertEqual(record["status"], "cleanup_unknown")
        request = dict(
            head="branch", base="develop", title="title", body="body", marker="marker"
        )
        self.assertEqual(
            PullRequestPublicationRequest(**request).to_payload(),
            {**request, "draft": True},
        )
