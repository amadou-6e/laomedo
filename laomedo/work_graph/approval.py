"""Protected local approval authority for Work Graph launch grants (#95).

Any process may *submit* a launch request. A grant exists only after a
registered WebAuthn authenticator signs a fresh challenge bound to that exact
request's canonical digest, with user presence and user verification. The
ledger stores the full assertion, and every redemption **re-verifies it**
against the registered credential (the trust anchor) and the stored request.
A same-user process that writes the ledger directly therefore cannot create a
redeemable grant without the authenticator's private key.

The trust anchor file and this code are the assets an OS boundary must protect
(a dedicated service identity and ACLs). This module does not create that
boundary; it makes it the *only* thing left to protect.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import secrets
import sqlite3

from laomedo.workflow_run_store import LaunchError

from .grants import _private_path
from .webauthn import AssertionError_, b64url_decode, b64url_encode, verify_assertion


CHALLENGE_SECONDS = 300
REQUEST_FIELDS = ("work_key", "work_url", "body_digest", "content_digest",
                  "graph_snapshot_id", "runner", "scope", "expires_at",
                  "timeout_seconds", "max_turns")


def _canonical(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def request_digest(request: dict) -> str:
    return "sha256:" + sha256(_canonical(request).encode("utf-8")).hexdigest()


def derive_challenge(request_id: str, nonce: bytes, digest: str) -> bytes:
    """Bind the WebAuthn challenge to the exact request, so the signature does too."""
    return sha256(b"laomedo-approval-v1\0" + request_id.encode("ascii") + b"\0" +
                  nonce + b"\0" + digest.encode("ascii")).digest()


def validate_request(request: dict) -> dict:
    """Return the canonical request, refusing missing or out-of-range fields."""
    if not isinstance(request, dict) or set(request) != set(REQUEST_FIELDS):
        raise LaunchError("approval_request_invalid")
    if not all(isinstance(request[key], str) and request[key]
               for key in REQUEST_FIELDS if key not in ("timeout_seconds", "max_turns")):
        raise LaunchError("approval_request_invalid")
    if (request["runner"] != "langflow-local" or request["scope"] != "stage-launch" or
            type(request["timeout_seconds"]) is not int or
            not 1 <= request["timeout_seconds"] <= 3600 or
            type(request["max_turns"]) is not int or not 0 <= request["max_turns"] <= 100):
        raise LaunchError("approval_request_invalid")
    try:
        expiry = datetime.fromisoformat(request["expires_at"])
    except ValueError:
        raise LaunchError("approval_request_invalid") from None
    if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
        raise LaunchError("approval_request_expired")
    return dict(request)


class TrustAnchor:
    """A registered ES256 WebAuthn credential and its relying-party context."""

    def __init__(self, *, credential_id: str, x: int, y: int, rp_id: str, origin: str):
        self.credential_id, self.point = credential_id, (x, y)
        self.rp_id, self.origin = rp_id, origin
        self.fingerprint = "sha256:" + sha256(_canonical({
            "credential_id": credential_id, "x": f"{x:064x}", "y": f"{y:064x}",
            "rp_id": rp_id, "origin": origin, "alg": "ES256"}).encode()).hexdigest()

    @classmethod
    def load(cls, path: Path) -> "TrustAnchor":
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
            if data.get("alg") != "ES256":
                raise ValueError
            return cls(credential_id=data["credential_id"], x=int(data["x"], 16),
                       y=int(data["y"], 16), rp_id=data["rp_id"], origin=data["origin"])
        except (OSError, ValueError, KeyError, TypeError):
            raise LaunchError("approval_trust_anchor_unavailable") from None


class ProtectedApprovalAuthority:
    def __init__(self, ledger: Path, anchor: TrustAnchor, *, pinned_fingerprint: str | None = None):
        if pinned_fingerprint is not None and pinned_fingerprint != anchor.fingerprint:
            raise LaunchError("approval_trust_anchor_changed")
        self.anchor = anchor
        self.path = _private_path(ledger)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as db, db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS requests (
                request_id TEXT PRIMARY KEY, request_json TEXT NOT NULL,
                request_digest TEXT NOT NULL, nonce TEXT NOT NULL UNIQUE,
                challenge_expires_at TEXT NOT NULL,
                state TEXT NOT NULL CHECK (state IN ('pending','approved','denied','expired')),
                created_at TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS grants (
                grant_id TEXT PRIMARY KEY,
                request_id TEXT NOT NULL UNIQUE REFERENCES requests(request_id),
                credential_id TEXT NOT NULL, authenticator_data TEXT NOT NULL,
                client_data_json TEXT NOT NULL, signature TEXT NOT NULL,
                sign_count INTEGER NOT NULL, anchor_fingerprint TEXT NOT NULL,
                approved_at TEXT NOT NULL, redeemed_at TEXT);
            CREATE TABLE IF NOT EXISTS counters (
                credential_id TEXT PRIMARY KEY, sign_count INTEGER NOT NULL);
            """)

    def _connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    # ---- submission (any process) -------------------------------------
    def submit(self, request: dict) -> dict:
        canonical = validate_request(request)
        request_id = "req-" + secrets.token_hex(16)
        nonce = secrets.token_bytes(32)
        digest = request_digest(canonical)
        challenge = derive_challenge(request_id, nonce, digest)
        expires = datetime.now(timezone.utc) + timedelta(seconds=CHALLENGE_SECONDS)
        with closing(self._connect()) as db, db:
            db.execute("INSERT INTO requests VALUES (?, ?, ?, ?, ?, 'pending', ?)",
                       (request_id, _canonical(canonical), digest,
                        b64url_encode(nonce), expires.isoformat(),
                        datetime.now(timezone.utc).isoformat()))
        return {"request_id": request_id, "request_digest": request_digest(canonical),
                "challenge": b64url_encode(challenge),
                "challenge_expires_at": expires.isoformat(), "request": canonical}

    def deny(self, request_id: str) -> None:
        with closing(self._connect()) as db, db:
            db.execute("UPDATE requests SET state='denied' WHERE request_id=? AND state='pending'",
                       (request_id,))

    # ---- approval (requires the authenticator) ------------------------
    def _verify(self, request_row, assertion: dict) -> int:
        if assertion.get("credential_id") != self.anchor.credential_id:
            raise LaunchError("approval_unknown_credential")
        try:
            # Recompute from the stored request itself; never trust a stored
            # challenge or digest column on its own.
            challenge = derive_challenge(
                request_row["request_id"], b64url_decode(request_row["nonce"]),
                request_digest(json.loads(request_row["request_json"])))
            return verify_assertion(
                public_point=self.anchor.point, rp_id=self.anchor.rp_id,
                origin=self.anchor.origin, challenge=challenge,
                authenticator_data=b64url_decode(assertion["authenticator_data"]),
                client_data_json=b64url_decode(assertion["client_data_json"]),
                signature=b64url_decode(assertion["signature"]))
        except (AssertionError_, KeyError, TypeError, ValueError) as exc:
            reason = str(exc) if isinstance(exc, AssertionError_) else "assertion_malformed"
            raise LaunchError("approval_" + reason) from None

    def approve(self, request_id: str, assertion: dict) -> str:
        """Consume the request's challenge and mint exactly one grant, atomically."""
        if not isinstance(assertion, dict):
            raise LaunchError("approval_assertion_malformed")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT * FROM requests WHERE request_id=?",
                             (request_id,)).fetchone()
            if row is None or row["state"] != "pending":
                raise LaunchError("approval_request_not_pending")
            if datetime.fromisoformat(row["challenge_expires_at"]) <= datetime.now(timezone.utc):
                db.execute("UPDATE requests SET state='expired' WHERE request_id=?", (request_id,))
                db.commit()
                raise LaunchError("approval_challenge_expired")
            if request_digest(json.loads(row["request_json"])) != row["request_digest"]:
                raise LaunchError("approval_request_tampered")
            count = self._verify(row, assertion)
            stored = db.execute("SELECT sign_count FROM counters WHERE credential_id=?",
                                (self.anchor.credential_id,)).fetchone()
            previous = stored["sign_count"] if stored else 0
            if (count or previous) and count <= previous:
                raise LaunchError("approval_counter_regressed")
            grant_id = "grant-" + secrets.token_hex(16)
            db.execute("UPDATE requests SET state='approved' WHERE request_id=? AND state='pending'",
                       (request_id,))
            db.execute("INSERT INTO grants VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                       (grant_id, request_id, assertion["credential_id"],
                        assertion["authenticator_data"], assertion["client_data_json"],
                        assertion["signature"], count, self.anchor.fingerprint,
                        datetime.now(timezone.utc).isoformat()))
            db.execute("INSERT INTO counters VALUES (?, ?) ON CONFLICT(credential_id) "
                       "DO UPDATE SET sign_count=excluded.sign_count",
                       (self.anchor.credential_id, count))
        return grant_id

    def grant_for(self, request_id: str) -> str | None:
        """Read-only recovery after a lost approval response; never mints."""
        with closing(self._connect()) as db:
            row = db.execute("SELECT grant_id FROM grants WHERE request_id=?",
                             (request_id,)).fetchone()
        return row["grant_id"] if row else None

    # ---- redemption (launch path) --------------------------------------
    def __call__(self, grant_id, binding):
        """Re-verify the stored assertion, check the binding, consume once."""
        if not isinstance(grant_id, str) or not isinstance(binding, dict):
            raise LaunchError("grant_invalid")
        with closing(self._connect()) as db, db:
            db.execute("BEGIN IMMEDIATE")
            grant = db.execute("SELECT * FROM grants WHERE grant_id=?", (grant_id,)).fetchone()
            if grant is None or grant["redeemed_at"] is not None:
                raise LaunchError("grant_invalid")
            row = db.execute("SELECT * FROM requests WHERE request_id=?",
                             (grant["request_id"],)).fetchone()
            if row is None or row["state"] != "approved":
                raise LaunchError("grant_invalid")
            request = json.loads(row["request_json"])
            # The digest is recomputed and the signature re-verified here, so an
            # edited or forged ledger row is not trusted on its own.
            if (request_digest(request) != row["request_digest"] or
                    grant["anchor_fingerprint"] != self.anchor.fingerprint):
                raise LaunchError("grant_record_untrusted")
            self._verify(row, {"credential_id": grant["credential_id"],
                               "authenticator_data": grant["authenticator_data"],
                               "client_data_json": grant["client_data_json"],
                               "signature": grant["signature"]})
            if (request["work_key"] != binding.get("work_snapshot", {}).get("key") or
                    request["content_digest"] != binding.get("selected_content_digest")):
                raise LaunchError("grant_binding_mismatch")
            if datetime.fromisoformat(request["expires_at"]) <= datetime.now(timezone.utc):
                raise LaunchError("grant_expired")
            updated = db.execute("UPDATE grants SET redeemed_at=? WHERE grant_id=? "
                                 "AND redeemed_at IS NULL",
                                 (datetime.now(timezone.utc).isoformat(), grant_id))
            if updated.rowcount != 1:
                raise LaunchError("grant_invalid")
        return {"grant_id": grant_id, "operator_authorized": True,
                "approval": "webauthn-es256", "request_id": grant["request_id"],
                "request_digest": row["request_digest"],
                "work_key": request["work_key"], "content_digest": request["content_digest"],
                "graph_snapshot_id": request["graph_snapshot_id"],
                "runner": request["runner"], "scope": request["scope"],
                "expires_at": request["expires_at"],
                "limits": {"timeout_seconds": request["timeout_seconds"],
                           "max_turns": request["max_turns"]}}
