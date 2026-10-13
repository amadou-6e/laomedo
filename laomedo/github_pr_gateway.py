"""Live PR discovery and graph operations through existing mediation grants."""
from datetime import datetime, timezone
from contextlib import closing
import json
from hashlib import sha256
import re
from .github_pr_contract import repository_from_url, labels_value, pr_digest, validate_patch
from .github_mediation import MediationError, KnownRejected


class GitHubPRGateway:
    def __init__(self, transports, mediation, grant_resolver):
        self.transports = transports  # Host-owned repository -> credential-bearing transport.
        self.mediation = mediation
        self.grant_resolver = grant_resolver  # Opaque ref -> token/run identity, never exposed.
        with closing(mediation._connect()) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS pr_node_intents (
                grant_ref TEXT NOT NULL, request_id TEXT NOT NULL, input_hash TEXT NOT NULL,
                payload TEXT NOT NULL, result TEXT, PRIMARY KEY(grant_ref,request_id))""")

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
        available = labels_value([item["name"] for item in transport(repository, "label_list", {})["items"]])
        if not set(labels) <= set(available):
            raise ValueError("selected_label_unavailable")
        prs = transport(repository, "pr_node_query", {"labels": labels, "state": state})["items"]
        return {"labels": available, "prs": [{"number": item["number"],
            "choice": "#" + str(item["number"]) + " " + item["title"], "title": item["title"]} for item in prs]}

    def _finish(self, key, result):
        with closing(self.mediation._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            prior = db.execute("SELECT result FROM pr_node_intents WHERE grant_ref=? AND request_id=?", key).fetchone()
            if prior and prior[0]:
                previous = json.loads(prior[0])
                if previous["operation"]["status"] in {"succeeded", "failed"} and result["operation"]["status"] == "unknown":
                    return previous
            db.execute("UPDATE pr_node_intents SET result=? WHERE grant_ref=? AND request_id=?",
                       (json.dumps(result), *key))
        return result

    def execute(self, repository_url, labels, state, pr_number, operation=None):
        repository, transport = self._transport(repository_url)
        labels = labels_value(labels)
        if state not in {"open", "closed", "all"} or type(pr_number) is not int or pr_number < 1:
            raise ValueError("selected_pr_invalid")
        key = None
        prior = None
        grant = None
        if operation is not None:
            try:
                operation = json.loads(json.dumps(operation, ensure_ascii=False, allow_nan=False))
            except (ValueError, TypeError):
                raise ValueError("pr_operation_invalid") from None
            if (not isinstance(operation, dict) or
                    set(operation) not in ({"action", "request_id", "grant_ref"}, {"action", "request_id", "grant_ref", "changes"}) or
                    operation.get("action") not in {"close", "modify"} or
                    any(not isinstance(operation.get(k), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", operation[k])
                        for k in ("request_id", "grant_ref"))):
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
                if (not isinstance(grant, dict) or grant.get("repository") != repository or
                        not isinstance(grant.get("token"), str) or not isinstance(grant.get("run_id"), str)):
                    raise ValueError()
                with closing(self.mediation._connect()) as db:
                    authenticated = db.execute("SELECT grant_id,run_id,repository FROM grants WHERE token_hash=?",
                        (sha256(grant["token"].encode()).hexdigest(),)).fetchone()
                if authenticated is None or authenticated["run_id"] != grant["run_id"] or authenticated["repository"] != repository:
                    raise ValueError()
            except Exception:
                raise ValueError("pr_grant_unavailable") from None
            input_hash = pr_digest({"repository": repository, "number": pr_number,
                "labels": labels, "state": state, "operation": operation,
                "binding": {"grant_id": authenticated["grant_id"], "run_id": authenticated["run_id"]}})
            with closing(self.mediation._connect()) as db, db:
                prior = db.execute("SELECT input_hash,payload,result FROM pr_node_intents WHERE grant_ref=? AND request_id=?", key).fetchone()
            if prior:
                if prior[0] != input_hash:
                    raise ValueError("pr_operation_conflict")
                if prior[2] is not None:
                    return json.loads(prior[2])
            existing = self.mediation.effect(grant["run_id"], operation["request_id"])
            if existing is not None:
                status = {"confirmed": "succeeded", "rejected": "failed"}.get(existing["state"], "unknown")
                pr = json.loads(existing["result_json"]) if existing.get("result_json") else None
                return self._finish(key, self._result(pr, status, "operation_previous_attempt")) if prior else self._result(None, "unknown", "pr_operation_conflict")
        pr = transport(repository, "pr_node_read", {"number": pr_number})
        if not set(labels) <= set(pr["labels"]) or (state != "all" and pr["state"] != state):
            raise ValueError("selected_pr_no_longer_matches")
        if operation is None:
            return self._result(pr, "not_requested")
        payload = json.loads(prior[1]) if prior else {"number": pr_number, "changes": changes,
            "expected": pr_digest(pr), "head": pr["head"]["branch"], "base": pr["base"]}
        if prior is None:
            with closing(self.mediation._connect()) as db, db:
                db.execute("BEGIN IMMEDIATE")
                concurrent = db.execute("SELECT input_hash,payload,result FROM pr_node_intents WHERE grant_ref=? AND request_id=?", key).fetchone()
                if concurrent:
                    if concurrent[0] != input_hash:
                        raise ValueError("pr_operation_conflict")
                    if concurrent[2]:
                        return json.loads(concurrent[2])
                    payload = json.loads(concurrent[1])
                else:
                    db.execute("INSERT INTO pr_node_intents VALUES (?,?,?,?,NULL)", (*key, input_hash, json.dumps(payload)))
        def before_write():
            try:
                with closing(self.mediation._connect()) as db:
                    self.mediation._grant(db, grant["token"], repository, "pr_node_update")
            except MediationError as error:
                raise KnownRejected(error.code) from None
        def scoped_transport(repo, action, body, **binding):
            return transport(repo, action, body, before_write=before_write, **binding)
        try:
            result = self.mediation.invoke(token=grant["token"], repository=repository,
                operation="pr_node_update", payload=payload, effect_id=operation["request_id"], transport=scoped_transport)
            status = {"confirmed": "succeeded", "rejected": "failed"}.get(result["state"], "unknown")
            updated = result.get("result") if status == "succeeded" else pr
            category = result.get("error") if status == "failed" else "pr_write_unknown" if status == "unknown" else None
            response = self._result(updated, status, category)
        except MediationError as error:
            response = self._result(pr, "failed", error.code)
        return self._finish(key, response)

    @staticmethod
    def _result(pr, status, category=None):
        return {"schema_version": "laomedo.github-pr.v1", "pr": pr,
            "fetched_at": datetime.now(timezone.utc).isoformat(), "content_digest": pr_digest(pr) if pr else None,
            "operation": {"status": status, "error_category": category}}
