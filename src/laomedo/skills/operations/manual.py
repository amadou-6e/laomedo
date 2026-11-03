"""Explicit local manual editing and reviewed registry publication.

Uses the existing proposal journal and registry CAS. Persist capabilities before
applying, and frozen publication drafts before promotion, so lost responses can
be reconciled without inventing a new write. This is trusted single-user state.
"""

from datetime import datetime, timezone
import json

from laomedo.skills.operations.models import (
    ManualPublicationReceipt,
    ManualSkillPermissions,
    ManualSkillPublication,
    ManualSkillSave,
    ManualSkillState,
)
from laomedo.skills.registry.errors import ConflictError, SkillStoreError
from laomedo.skills.registry.files import inventory, read_json
from laomedo.skills.registry.hashing import canonical_json
from laomedo.skills.registry.policy import validate_draft, validate_policy


class ManualSkillEditor:
    """Own manual permissions, save reconciliation and exact reviewed publication."""

    def __init__(self, operations, permissions=None):
        self.operations = operations
        self.permissions = {
            skill: ManualSkillPermissions(**grant)
            for skill, grant in (permissions or {}).items()
        }
        with operations.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS manual_saves (
                    request TEXT PRIMARY KEY, payload TEXT NOT NULL,
                    ticket TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS manual_publications (
                    skill TEXT NOT NULL, commit_id TEXT NOT NULL, base TEXT NOT NULL,
                    draft TEXT NOT NULL, policy TEXT NOT NULL, result TEXT,
                    PRIMARY KEY(skill, commit_id, base));
            """)

    def _policy(self, skill, action):
        grant = self.permissions.get(skill, ManualSkillPermissions())
        policy = self.operations.policies.get(skill)
        if not getattr(grant, action) or policy is None:
            raise SkillStoreError("skill_manual_not_authorized")
        validate_policy(policy)
        return policy

    def editor(self, skill_id, revision_id):
        """Read exact head/current bindings and grants; never return tickets or policy content."""
        history = self.operations.history(skill_id, revision_id)
        head = history["commits"][0]
        current = self.operations.store.revision(skill_id)
        grant = self.permissions.get(skill_id, ManualSkillPermissions())
        configured = skill_id in self.operations.policies
        return ManualSkillState(
            skill_id=skill_id,
            selected_revision=revision_id,
            head_revision=head["revision_id"],
            head_commit=head["commit_id"],
            latest_revision=current["revision_id"],
            can_edit=grant.edit and configured and head["revision_id"] == revision_id,
            can_publish=grant.publish
            and configured
            and head["revision_id"] == revision_id,
            edit_enabled=grant.edit and configured,
        ).model_dump()

    def save(self, **payload):
        """Bind UUID to exact proposal before applying; reconcile an already committed save."""
        save = ManualSkillSave.model_validate(payload)
        encoded = canonical_json(save.to_record()).decode()
        with self.operations.connect() as db:
            existing = db.execute(
                "SELECT * FROM manual_saves WHERE request=?", (save.request_id,)
            ).fetchone()
        result = self._saved_result(existing, save, encoded)
        if result is not None:
            return result
        self._policy(save.skill_id, "edit")
        if existing is None:
            reservation = self.operations.prepare(
                save.skill_id, save.revision_id, save.commit_id
            )
            with self.operations.connect() as db:
                db.execute(
                    "INSERT OR IGNORE INTO manual_saves VALUES (?,?,?)",
                    (save.request_id, encoded, reservation["ticket"]),
                )
                existing = db.execute(
                    "SELECT * FROM manual_saves WHERE request=?", (save.request_id,)
                ).fetchone()
        result = self._saved_result(existing, save, encoded)
        if result is not None:
            return result
        return self.operations.apply(
            existing["ticket"], save.operation.to_payload(), {"kind": "operator"}
        )

    def _saved_result(self, existing, save, encoded):
        """Read an exact completed receipt without granting another mutation."""
        if existing is None:
            return None
        if existing["payload"] != encoded:
            raise ConflictError("skill_manual_request_conflict")
        # apply's normal capability expiry remains unchanged. A retained result is
        # read-only reconciliation, not a fresh use of an expired capability.
        with self.operations.connect() as db:
            applied = db.execute(
                "SELECT proposal,result FROM requests WHERE ticket=?",
                (existing["ticket"],),
            ).fetchone()
        if applied and applied["result"]:
            if json.loads(applied["proposal"]) != save.operation.to_payload():
                raise ConflictError("skill_manual_request_conflict")
            return json.loads(applied["result"])
        return None

    def _publication_draft(self, publication, policy):
        """Freeze the cumulative canonical-to-candidate diff under the current policy."""
        store = self.operations.store
        latest = store.revision(publication.skill_id)
        if latest["revision_id"] != publication.expected_latest:
            raise ConflictError("skill_manual_stale")
        if publication.revision_id == publication.expected_latest:
            raise SkillStoreError("skill_manual_nothing_to_publish")
        before = inventory(
            store._revision_dir(publication.skill_id, publication.expected_latest)
            / "bundle"
        )
        after = inventory(
            store._revision_dir(publication.skill_id, publication.revision_id)
            / "bundle"
        )
        if validate_draft(before, after, policy):
            raise SkillStoreError("skill_manual_policy_denied")
        draft = store.create_draft(
            publication.skill_id, publication.expected_latest, policy
        )
        workspace = store.draft_workspace(draft["draft_id"])
        for path in before.keys() - after.keys():
            (workspace / path).unlink()
        for folder in sorted(
            (p for p in workspace.rglob("*") if p.is_dir()),
            key=lambda p: len(p.parts),
            reverse=True,
        ):
            if not any(folder.iterdir()):
                folder.rmdir()
        for path, content in after.items():
            target = workspace / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
        frozen = store.freeze_draft(draft["draft_id"], editor_kind="operator")
        if (
            not frozen["promotion_eligible"]
            or frozen["proposed_tree_hash"] != publication.revision_id
        ):
            raise SkillStoreError("skill_manual_policy_denied")
        return draft["draft_id"]

    def _published(self, row, publication):
        """Reconcile the registry's durable promotion log without rewriting latest."""
        path = (
            self.operations.store._skill(publication.skill_id)
            / "promotions"
            / (row["draft"] + ".json")
        )
        if not path.exists():
            return False
        record = read_json(path)
        if (
            record.get("draft_id") != row["draft"]
            or record.get("base_revision") != publication.expected_latest
            or record.get("promoted_revision") != publication.revision_id
            or record.get("policy_ref", {}).get("hash") != row["policy"]
        ):
            raise SkillStoreError("skill_manual_unavailable")
        self.operations.store.revision(publication.skill_id, publication.revision_id)
        return True

    def publish(self, **payload):
        """Promote the exact reviewed head once; replay its durable receipt after uncertainty."""
        publication = ManualSkillPublication.model_validate(payload)
        identity = (
            publication.skill_id,
            publication.commit_id,
            publication.expected_latest,
        )
        with self.operations.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM manual_publications WHERE skill=? AND commit_id=? AND base=?",
                identity,
            ).fetchone()
            commit = self.operations._read(
                db, publication.skill_id, publication.commit_id
            )
            if commit["revision_id"] != publication.revision_id:
                raise ConflictError("skill_manual_stale")
            if row and row["result"]:
                return json.loads(row["result"])
            head = db.execute(
                "SELECT id FROM heads WHERE skill=?", (publication.skill_id,)
            ).fetchone()
            if (not head or head["id"] != publication.commit_id) and not (
                row and self._published(row, publication)
            ):
                raise ConflictError("skill_manual_stale")
            if row is None:
                policy = self._policy(publication.skill_id, "publish")
                policy_hash = validate_policy(policy)["hash"]
                draft = self._publication_draft(publication, policy)
                db.execute(
                    "INSERT INTO manual_publications VALUES (?,?,?,?,?,NULL)",
                    (*identity, draft, policy_hash),
                )
                row = db.execute(
                    "SELECT * FROM manual_publications WHERE skill=? AND commit_id=? AND base=?",
                    identity,
                ).fetchone()
        # Persisted before this filesystem CAS. A crash after promotion can use
        # the same draft and existing store recovery path on the next request.
        with self.operations.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute(
                "SELECT result FROM manual_publications WHERE skill=? AND commit_id=? AND base=?",
                identity,
            ).fetchone()
            if existing["result"]:
                return json.loads(existing["result"])
            if not self._published(row, publication):
                policy_hash = validate_policy(
                    self._policy(publication.skill_id, "publish")
                )["hash"]
                if row["policy"] != policy_hash:
                    raise SkillStoreError("skill_manual_policy_denied")
                head = db.execute(
                    "SELECT id FROM heads WHERE skill=?", (publication.skill_id,)
                ).fetchone()
                if not head or head["id"] != publication.commit_id:
                    raise ConflictError("skill_manual_stale")
                self.operations.store.promote_draft(
                    row["draft"],
                    expected_base_revision=publication.expected_latest,
                    reviewed_draft_hash=publication.revision_id,
                    expected_policy_hash=policy_hash,
                )
            result = ManualPublicationReceipt(
                skill_id=publication.skill_id,
                revision_id=publication.revision_id,
                commit_id=publication.commit_id,
                previous_revision=publication.expected_latest,
                confirmed_at=datetime.now(timezone.utc).isoformat(),
            ).model_dump()
            db.execute(
                "UPDATE manual_publications SET result=? WHERE skill=? AND commit_id=? AND base=?",
                (json.dumps(result), *identity),
            )
        return result
