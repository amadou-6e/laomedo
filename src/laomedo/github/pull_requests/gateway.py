"""Live PR discovery and graph operations through existing mediation grants."""

from laomedo.github.models import GitHubOperationIntent, GitHubGrantBinding
from laomedo.github.pull_requests.models import PullRequestFeedbackContext

from contextlib import closing
from datetime import datetime
from datetime import timezone
from hashlib import sha256
import json
from laomedo.github.contract import labels_value
from laomedo.github.contract import repository_from_url
from laomedo.github.contract import issue_digest as pr_digest
from laomedo.github.pull_requests.contract import validate_patch
from laomedo.host.mediation.errors import KnownRejected
from laomedo.host.mediation.errors import MediationError
import re
import secrets


class GitHubPRGateway:
    def __init__(self, transports, mediation, grant_resolver, *, feedback_grants=None):
        self.transports = (
            transports  # Host-owned repository -> credential-bearing transport.
        )
        self.mediation = mediation
        self.grant_resolver = (
            grant_resolver  # Opaque ref -> token/run identity, never exposed.
        )
        self.feedback_grants = dict(
            feedback_grants or {}
        )  # Host-only repo#PR -> grant ref.
        with closing(mediation._connect()) as db, db:
            db.execute(
                """CREATE TABLE IF NOT EXISTS pr_node_intents (
                grant_ref TEXT NOT NULL, request_id TEXT NOT NULL, input_hash TEXT NOT NULL,
                payload TEXT NOT NULL, result TEXT, PRIMARY KEY(grant_ref,request_id))"""
            )
            db.execute("""CREATE TABLE IF NOT EXISTS pr_feedback_tickets (
                ticket TEXT PRIMARY KEY, request_id TEXT NOT NULL UNIQUE,
                grant_ref TEXT NOT NULL, binding_digest TEXT NOT NULL,
                context TEXT NOT NULL, expires REAL NOT NULL)""")

    def _feedback_binding(self, ref, pr):
        try:
            binding = self.grant_resolver(ref)
            if binding["repository"] != pr["repository"]:
                raise ValueError()
            with closing(self.mediation._connect()) as db:
                grant = self.mediation._grant(
                    db, binding["token"], pr["repository"], "pr_node_update"
                )
                target = db.execute(
                    "SELECT base FROM pr_targets WHERE grant_id=? AND number=?",
                    (grant["grant_id"], pr["number"]),
                ).fetchone()
            if (
                binding["run_id"] != grant["run_id"]
                or target is None
                or target["base"] != pr["base"]
                or grant["branch"] != pr["head"]["branch"]
                or pr["head"]["repository"] != pr["repository"]
            ):
                raise ValueError()
            return pr_digest(
                {
                    "grant_id": grant["grant_id"],
                    "run_id": grant["run_id"],
                    "token_hash": sha256(binding["token"].encode()).hexdigest(),
                }
            )
        except Exception:
            raise ValueError("pr_grant_unavailable") from None

    def prepare_feedback(self, repository_url, labels, state, pr_number, expected):
        """Reserve trusted identity before the model; never put this ticket in its task."""
        initial = self.execute(repository_url, labels, state, pr_number)
        if not isinstance(expected, str) or initial["content_digest"] != expected:
            raise ValueError("pr_changed_since_agent_read")
        pr = initial["pr"]
        ref = self.feedback_grants.get(f"{pr['repository']}#{pr['number']}")
        if not isinstance(ref, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", ref):
            raise ValueError("pr_feedback_not_configured")
        binding_digest = self._feedback_binding(ref, pr)
        ticket, request_id = secrets.token_hex(32), "pr-feedback-" + secrets.token_hex(
            24
        )
        issued_monotonic = self.mediation.monotonic()
        context = PullRequestFeedbackContext(
            repository_url=repository_url,
            labels=labels,
            state=state,
            pr_number=pr_number,
            expected=expected,
            pr=pr,
            issued_monotonic=issued_monotonic,
            expires_monotonic=issued_monotonic + 300,
        ).to_payload()
        with closing(self.mediation._connect()) as db, db:
            db.execute(
                "INSERT INTO pr_feedback_tickets VALUES (?,?,?,?,?,?)",
                (
                    ticket,
                    request_id,
                    ref,
                    binding_digest,
                    json.dumps(context),
                    self.mediation.now() + 300,
                ),
            )
        return {"schema_version": "laomedo.pr-feedback-ticket.v1", "ticket": ticket}

    def apply_feedback(self, ticket, operation):
        if not isinstance(ticket, str) or not re.fullmatch(r"[0-9a-f]{64}", ticket):
            raise ValueError("pr_feedback_ticket_invalid")
        if (
            not isinstance(operation, dict)
            or operation.get("action") not in {"modify", "close"}
            or set(operation)
            != (
                {"action", "changes"}
                if operation.get("action") == "modify"
                else {"action"}
            )
        ):
            raise ValueError("pr_operation_invalid")
        if operation["action"] == "modify":
            patch = validate_patch(operation["changes"])
            if "state" in patch:
                raise ValueError("pr_patch_invalid")
        with closing(self.mediation._connect()) as db:
            row = db.execute(
                "SELECT * FROM pr_feedback_tickets WHERE ticket=?", (ticket,)
            ).fetchone()
        if row is None or self.mediation.now() >= row["expires"]:
            raise ValueError("pr_feedback_ticket_invalid")
        context = json.loads(row["context"])
        issued = context.pop("issued_monotonic", None)
        deadline = context.pop("expires_monotonic", None)
        now_monotonic = self.mediation.monotonic()
        if (
            not isinstance(issued, (int, float))
            or not isinstance(deadline, (int, float))
            or now_monotonic < issued
            or now_monotonic >= deadline
        ):
            raise ValueError("pr_feedback_ticket_invalid")
        pr = context.pop("pr")
        if (
            self.feedback_grants.get(f"{pr['repository']}#{pr['number']}")
            != row["grant_ref"]
        ):
            raise ValueError("pr_feedback_not_configured")
        if self._feedback_binding(row["grant_ref"], pr) != row["binding_digest"]:
            raise ValueError("pr_grant_unavailable")
        stamped = {
            **operation,
            "request_id": row["request_id"],
            "grant_ref": row["grant_ref"],
        }
        return self.execute(**context, operation=stamped)

    def _transport(self, repository_url):
        repository = repository_from_url(repository_url)
        if repository not in self.transports:
            raise ValueError("repository_connection_unavailable")
        return repository, self.transports[repository]

    def discover(self, repository_url, labels, state="open"):
        repository, transport = self._transport(repository_url)
        labels = labels_value(labels)
        if state not in {"open", "closed", "all"}:
            raise ValueError("pr_state_invalid")
        available = labels_value(
            [item["name"] for item in transport(repository, "label_list", {})["items"]]
        )
        if not set(labels) <= set(available):
            raise ValueError("selected_label_unavailable")
        prs = transport(
            repository, "pr_node_query", {"labels": labels, "state": state}
        )["items"]
        return {
            "labels": available,
            "prs": [
                {
                    "number": item["number"],
                    "choice": "#" + str(item["number"]) + " " + item["title"],
                    "title": item["title"],
                }
                for item in prs
            ],
        }

    def _finish(self, key, result):
        with closing(self.mediation._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute(
                "SELECT result FROM pr_node_intents WHERE grant_ref=? AND request_id=?",
                key,
            ).fetchone()
            if prior and prior[0]:
                previous = json.loads(prior[0])
                if (
                    previous["operation"]["status"] in {"succeeded", "failed"}
                    and result["operation"]["status"] == "unknown"
                ):
                    return previous
            db.execute(
                "UPDATE pr_node_intents SET result=? WHERE grant_ref=? AND request_id=?",
                (json.dumps(result), *key),
            )
        return result

    def execute(
        self, repository_url, labels, state, pr_number, operation=None, expected=None
    ):
        repository, transport = self._transport(repository_url)
        labels = labels_value(labels)
        if expected is not None and (
            not isinstance(expected, str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", expected)
        ):
            raise ValueError("invalid_request")
        if (
            state not in {"open", "closed", "all"}
            or type(pr_number) is not int
            or pr_number < 1
        ):
            raise ValueError("selected_pr_invalid")
        key = None
        prior = None
        grant = None
        if operation is not None:
            try:
                operation = json.loads(
                    json.dumps(operation, ensure_ascii=False, allow_nan=False)
                )
            except (ValueError, TypeError):
                raise ValueError("pr_operation_invalid") from None
            if (
                not isinstance(operation, dict)
                or set(operation)
                not in (
                    {"action", "request_id", "grant_ref"},
                    {"action", "request_id", "grant_ref", "changes"},
                )
                or operation.get("action") not in {"close", "modify"}
                or any(
                    not isinstance(operation.get(k), str)
                    or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", operation[k])
                    for k in ("request_id", "grant_ref")
                )
            ):
                raise ValueError("pr_operation_invalid")
            if operation["action"] == "close":
                if "changes" in operation:
                    raise ValueError("pr_operation_invalid")
                changes = {"state": "closed"}
            else:
                changes = validate_patch(operation.get("changes"))
                if "state" in changes:
                    raise ValueError("pr_operation_invalid")
            key = (operation["grant_ref"], operation["request_id"])
            try:
                grant = self.grant_resolver(operation["grant_ref"])
                if (
                    not isinstance(grant, dict)
                    or grant.get("repository") != repository
                    or not isinstance(grant.get("token"), str)
                    or not isinstance(grant.get("run_id"), str)
                ):
                    raise ValueError()
                with closing(self.mediation._connect()) as db:
                    authenticated = db.execute(
                        "SELECT grant_id,run_id,repository FROM grants WHERE token_hash=?",
                        (sha256(grant["token"].encode()).hexdigest(),),
                    ).fetchone()
                if (
                    authenticated is None
                    or authenticated["run_id"] != grant["run_id"]
                    or authenticated["repository"] != repository
                ):
                    raise ValueError()
            except Exception:
                raise ValueError("pr_grant_unavailable") from None
            input_hash = pr_digest(
                GitHubOperationIntent(
                    repository=repository,
                    number=pr_number,
                    labels=labels,
                    state=state,
                    operation=operation,
                    binding=GitHubGrantBinding(
                        grant_id=authenticated["grant_id"],
                        run_id=authenticated["run_id"],
                    ),
                ).to_payload()
            )
            with closing(self.mediation._connect()) as db, db:
                prior = db.execute(
                    "SELECT input_hash,payload,result FROM pr_node_intents WHERE grant_ref=? AND request_id=?",
                    key,
                ).fetchone()
            if prior:
                if prior[0] != input_hash:
                    raise ValueError("pr_operation_conflict")
                if prior[2] is not None:
                    return json.loads(prior[2])
            existing = self.mediation.effect(grant["run_id"], operation["request_id"])
            if existing is not None:
                status = {"confirmed": "succeeded", "rejected": "failed"}.get(
                    existing["state"], "unknown"
                )
                pr = (
                    json.loads(existing["result_json"])
                    if existing.get("result_json")
                    else None
                )
                return (
                    self._finish(
                        key, self._result(pr, status, "operation_previous_attempt")
                    )
                    if prior
                    else self._result(None, "unknown", "pr_operation_conflict")
                )
        pr = transport(repository, "pr_node_read", {"number": pr_number})
        if not set(labels) <= set(pr["labels"]) or (
            state != "all" and pr["state"] != state
        ):
            raise ValueError("selected_pr_no_longer_matches")
        if operation is None:
            return self._result(pr, "not_requested")
        if expected is not None and pr_digest(pr) != expected:
            raise ValueError("pr_changed_since_agent_read")
        payload = (
            json.loads(prior[1])
            if prior
            else {
                "number": pr_number,
                "changes": changes,
                "expected": pr_digest(pr),
                "head": pr["head"]["branch"],
                "base": pr["base"],
            }
        )
        if prior is None:
            with closing(self.mediation._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                concurrent = db.execute(
                    "SELECT input_hash,payload,result FROM pr_node_intents WHERE grant_ref=? AND request_id=?",
                    key,
                ).fetchone()
                if concurrent:
                    if concurrent[0] != input_hash:
                        raise ValueError("pr_operation_conflict")
                    if concurrent[2]:
                        return json.loads(concurrent[2])
                    payload = json.loads(concurrent[1])
                else:
                    db.execute(
                        "INSERT INTO pr_node_intents VALUES (?,?,?,?,NULL)",
                        (*key, input_hash, json.dumps(payload)),
                    )

        def before_write():
            try:
                with closing(self.mediation._connect()) as db:
                    self.mediation._grant(
                        db, grant["token"], repository, "pr_node_update"
                    )
            except MediationError as error:
                raise KnownRejected(error.code) from None

        def scoped_transport(repo, action, body, **binding):
            return transport(repo, action, body, before_write=before_write, **binding)

        try:
            result = self.mediation.invoke(
                token=grant["token"],
                repository=repository,
                operation="pr_node_update",
                payload=payload,
                effect_id=operation["request_id"],
                transport=scoped_transport,
            )
            status = {"confirmed": "succeeded", "rejected": "failed"}.get(
                result["state"], "unknown"
            )
            updated = result.get("result") if status == "succeeded" else pr
            category = (
                result.get("error")
                if status == "failed"
                else "pr_write_unknown" if status == "unknown" else None
            )
            response = self._result(updated, status, category)
        except MediationError as error:
            response = self._result(pr, "failed", error.code)
        return self._finish(key, response)

    @staticmethod
    def _result(pr, status, category=None):
        return {
            "schema_version": "laomedo.github-pr.v1",
            "pr": pr,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "content_digest": pr_digest(pr) if pr else None,
            "operation": {"status": status, "error_category": category},
        }
