"""Protected approval authority (#95) with a credential-free fixture authenticator."""

from contextlib import closing
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
from pathlib import Path
import secrets
import sqlite3
import tempfile
import unittest

from laomedo.work_graph import webauthn
from laomedo.work_graph.approval import (ProtectedApprovalAuthority, TrustAnchor,
                                         derive_challenge, request_digest)
from laomedo.work_graph.webauthn import b64url_decode, b64url_encode
from laomedo.workflow_run_store import LaunchError


RP_ID, ORIGIN = "laomedo.local", "https://laomedo.local"


class FixtureAuthenticator:
    """A software ES256 authenticator for tests only; never a real credential."""

    def __init__(self):
        self.private = secrets.randbelow(webauthn.N - 1) + 1
        self.public = webauthn.multiply(self.private, webauthn.G)
        self.credential_id = b64url_encode(secrets.token_bytes(16))
        self.counter = 0

    def anchor(self):
        return TrustAnchor(credential_id=self.credential_id, x=self.public[0],
                           y=self.public[1], rp_id=RP_ID, origin=ORIGIN)

    def _sign(self, message):
        digest = int.from_bytes(sha256(message).digest(), "big")
        while True:
            k = secrets.randbelow(webauthn.N - 1) + 1
            r = webauthn.multiply(k, webauthn.G)[0] % webauthn.N
            s = pow(k, -1, webauthn.N) * (digest + r * self.private) % webauthn.N
            if r and s:
                break

        def der(value):
            raw = value.to_bytes(32, "big").lstrip(b"\0") or b"\0"
            raw = b"\0" + raw if raw[0] & 0x80 else raw
            return b"\x02" + bytes([len(raw)]) + raw

        body = der(r) + der(s)
        return b"\x30" + bytes([len(body)]) + body

    def assert_(self, challenge, *, origin=ORIGIN, rp_id=RP_ID, flags=0x05,
                kind="webauthn.get"):
        self.counter += 1
        auth = (sha256(rp_id.encode()).digest() + bytes([flags]) +
                self.counter.to_bytes(4, "big"))
        client = json.dumps({"type": kind, "challenge": b64url_encode(challenge),
                             "origin": origin, "crossOrigin": False}).encode()
        return {"credential_id": self.credential_id,
                "authenticator_data": b64url_encode(auth),
                "client_data_json": b64url_encode(client),
                "signature": b64url_encode(self._sign(auth + sha256(client).digest()))}


def request(**changes):
    value = {"work_key": "github:S-20", "work_url": "https://github.com/o/r/issues/20",
             "body_digest": "sha256:" + "1" * 64, "content_digest": "sha256:" + "2" * 64,
             "task_digest": "sha256:" + sha256(b"Synthetic task").hexdigest(),
             "graph_snapshot_id": "sha256:" + "3" * 64, "runner": "langflow-local",
             "scope": "stage-launch",
             "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=10)).isoformat(),
             "timeout_seconds": 60, "max_turns": 0}
    value.update(changes)
    return value


def binding(req):
    return {"work_snapshot": {"key": req["work_key"]},
            "selected_content_digest": req["content_digest"]}


class ApprovalAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.ledger = Path(self.temp.name) / "approval.sqlite3"
        self.key = FixtureAuthenticator()
        self.authority = ProtectedApprovalAuthority(self.ledger, self.key.anchor())

    def approve(self, req=None):
        submitted = self.authority.submit(req or request())
        challenge = derive_challenge(submitted["request_id"],
                                     self._nonce(submitted["request_id"]),
                                     submitted["request_digest"])
        grant_id = self.authority.approve(submitted["request_id"],
                                          self.key.assert_(challenge))
        return submitted, grant_id

    def _nonce(self, request_id):
        with closing(sqlite3.connect(self.ledger)) as db:
            return b64url_decode(db.execute("SELECT nonce FROM requests WHERE request_id=?",
                                            (request_id,)).fetchone()[0])

    def test_submitted_challenge_is_bound_to_request(self):
        submitted = self.authority.submit(request())
        expected = derive_challenge(submitted["request_id"], self._nonce(submitted["request_id"]),
                                    submitted["request_digest"])
        self.assertEqual(b64url_decode(submitted["challenge"]), expected)
        self.assertEqual(submitted["request_digest"], request_digest(submitted["request"]))

    def test_service_review_refuses_corrupt_pending_record(self):
        submitted = self.authority.submit(request())
        with closing(sqlite3.connect(self.ledger)) as db, db:
            db.execute("UPDATE requests SET request_json=? WHERE request_id=?",
                       ("not-json", submitted["request_id"]))
        with self.assertRaisesRegex(LaunchError, "approval_request_tampered"):
            self.authority.pending_request(submitted["request_id"])

    def test_approved_grant_redeems_once_for_matching_binding(self):
        submitted, grant_id = self.approve()
        grant = self.authority(grant_id, binding(submitted["request"]))
        self.assertTrue(grant["operator_authorized"])
        self.assertEqual(grant["approval"], "webauthn-es256")
        self.assertEqual(grant["limits"], {"timeout_seconds": 60, "max_turns": 0})
        with self.assertRaisesRegex(LaunchError, "grant_invalid"):
            self.authority(grant_id, binding(submitted["request"]))

    def test_binding_mismatch_refuses_without_consuming(self):
        submitted, grant_id = self.approve()
        wrong = binding(submitted["request"])
        wrong["selected_content_digest"] = "sha256:" + "9" * 64
        with self.assertRaisesRegex(LaunchError, "grant_binding_mismatch"):
            self.authority(grant_id, wrong)
        self.assertTrue(self.authority(grant_id, binding(submitted["request"]))
                        ["operator_authorized"])

    def test_same_user_cannot_mint_by_writing_the_ledger(self):
        submitted = self.authority.submit(request())
        forged_auth = sha256(RP_ID.encode()).digest() + bytes([0x05]) + (7).to_bytes(4, "big")
        with closing(sqlite3.connect(self.ledger)) as db, db:
            db.execute("UPDATE requests SET state='approved' WHERE request_id=?",
                       (submitted["request_id"],))
            db.execute("INSERT INTO grants VALUES ('grant-forged', ?, ?, ?, ?, ?, 7, ?, ?, NULL)",
                       (submitted["request_id"], self.key.credential_id,
                        b64url_encode(forged_auth),
                        b64url_encode(json.dumps({"type": "webauthn.get",
                            "challenge": submitted["challenge"], "origin": ORIGIN}).encode()),
                        b64url_encode(b"\x30\x06\x02\x01\x01\x02\x01\x01"),
                        self.key.anchor().fingerprint, datetime.now(timezone.utc).isoformat()))
        with self.assertRaisesRegex(LaunchError, "approval_signature_invalid"):
            self.authority("grant-forged", binding(submitted["request"]))

    def test_editing_an_approved_request_invalidates_its_signature(self):
        submitted, grant_id = self.approve()
        edited = dict(submitted["request"], work_key="github:S-99")
        with closing(sqlite3.connect(self.ledger)) as db, db:
            db.execute("UPDATE requests SET request_json=?, request_digest=? WHERE request_id=?",
                       (json.dumps(edited, sort_keys=True, separators=(",", ":")),
                        request_digest(edited), submitted["request_id"]))
        with self.assertRaisesRegex(LaunchError, "approval_challenge_mismatch"):
            self.authority(grant_id, binding(edited))

    def test_assertion_cannot_be_replayed_onto_another_request(self):
        first = self.authority.submit(request())
        second = self.authority.submit(request())
        assertion = self.key.assert_(derive_challenge(
            first["request_id"], self._nonce(first["request_id"]), first["request_digest"]))
        with self.assertRaisesRegex(LaunchError, "approval_challenge_mismatch"):
            self.authority.approve(second["request_id"], assertion)
        self.authority.approve(first["request_id"], assertion)
        with self.assertRaisesRegex(LaunchError, "approval_request_not_pending"):
            self.authority.approve(first["request_id"], assertion)

    def test_lost_response_recovers_without_minting_a_second_grant(self):
        submitted, grant_id = self.approve()
        self.assertEqual(self.authority.grant_for(submitted["request_id"]), grant_id)
        with self.assertRaisesRegex(LaunchError, "approval_request_not_pending"):
            self.authority.approve(submitted["request_id"], self.key.assert_(b"x" * 32))
        with closing(sqlite3.connect(self.ledger)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM grants").fetchone()[0], 1)

    def test_reopen_preserves_one_grant_and_its_redemption(self):
        submitted, grant_id = self.approve()
        reopened = ProtectedApprovalAuthority(self.ledger, self.key.anchor())
        self.assertEqual(reopened.grant_for(submitted["request_id"]), grant_id)
        reopened(grant_id, binding(submitted["request"]))
        after_restart = ProtectedApprovalAuthority(self.ledger, self.key.anchor())
        with self.assertRaisesRegex(LaunchError, "grant_invalid"):
            after_restart(grant_id, binding(submitted["request"]))
        self.assertEqual(after_restart.grant_for(submitted["request_id"]), grant_id)

    def test_denied_and_expired_requests_cannot_be_approved(self):
        denied = self.authority.submit(request())
        self.authority.deny(denied["request_id"])
        with self.assertRaisesRegex(LaunchError, "approval_request_not_pending"):
            self.authority.approve(denied["request_id"], self.key.assert_(b"x" * 32))
        stale = self.authority.submit(request())
        with closing(sqlite3.connect(self.ledger)) as db, db:
            db.execute("UPDATE requests SET challenge_expires_at=? WHERE request_id=?",
                       ((datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat(),
                        stale["request_id"]))
        with self.assertRaisesRegex(LaunchError, "approval_challenge_expired"):
            self.authority.approve(stale["request_id"], self.key.assert_(b"x" * 32))
        with self.assertRaisesRegex(LaunchError, "approval_request_not_pending"):
            self.authority.approve(stale["request_id"], self.key.assert_(b"x" * 32))

    def test_ceremony_fields_are_each_enforced(self):
        cases = {"origin_mismatch": {"origin": "https://evil.local"},
                 "rp_id_mismatch": {"rp_id": "evil.local"},
                 "user_not_verified": {"flags": 0x01},
                 "user_not_present": {"flags": 0x04},
                 "wrong_ceremony_type": {"kind": "webauthn.create"}}
        for reason, changes in cases.items():
            submitted = self.authority.submit(request())
            challenge = derive_challenge(submitted["request_id"],
                                         self._nonce(submitted["request_id"]),
                                         submitted["request_digest"])
            with self.subTest(reason), self.assertRaisesRegex(LaunchError, reason):
                self.authority.approve(submitted["request_id"],
                                       self.key.assert_(challenge, **changes))

    def test_other_authenticator_and_changed_anchor_are_refused(self):
        submitted = self.authority.submit(request())
        challenge = derive_challenge(submitted["request_id"], self._nonce(submitted["request_id"]),
                                     submitted["request_digest"])
        stranger = FixtureAuthenticator()
        stranger.credential_id = self.key.credential_id   # same ID, different key
        with self.assertRaisesRegex(LaunchError, "approval_signature_invalid"):
            self.authority.approve(submitted["request_id"], stranger.assert_(challenge))
        with self.assertRaisesRegex(LaunchError, "approval_trust_anchor_changed"):
            ProtectedApprovalAuthority(self.ledger, FixtureAuthenticator().anchor(),
                                       pinned_fingerprint=self.key.anchor().fingerprint)

    def test_signature_counter_must_advance(self):
        self.approve()
        self.key.counter = 0   # a cloned authenticator replaying an old counter
        with self.assertRaisesRegex(LaunchError, "approval_counter_regressed"):
            self.approve()

    def test_residual_same_user_ledger_reset_replays_only_that_approval(self):
        """Documented limit: without the OS boundary, a same-user process can reset
        ``redeemed_at`` and re-redeem the *same* human-approved request until it
        expires. It still cannot create or alter an approval (tests above)."""
        submitted, grant_id = self.approve()
        self.authority(grant_id, binding(submitted["request"]))
        with closing(sqlite3.connect(self.ledger)) as db, db:
            db.execute("UPDATE grants SET redeemed_at=NULL WHERE grant_id=?", (grant_id,))
        replayed = self.authority(grant_id, binding(submitted["request"]))
        self.assertEqual(replayed["request_id"], submitted["request_id"])



class Es256KnownAnswerTests(unittest.TestCase):
    def test_rfc6979_p256_sha256_sample_vector(self):
        """RFC 6979 A.2.5: an independent check of the curve arithmetic."""
        private = 0xC9AFA9D845BA75166B5C215767B1D6934E50C3DB36E89B127B8A622B120F6721
        public = (0x60FED4BA255A9D31C961EB74C6356D68C049B8923B61FA6CE669622E60F29FB6,
                  0x7903FE1008B8BC99A41AE9E95628BC64F2F1B20C2D7E9F5177A3C294D4462299)
        r = 0xEFD48B2AACB6A8FD1140DD9CD45E81D69D2C877B56AAF991C34D0EA84EAF3716
        s = 0xF7CB1C942D657C41D436C7A1B6E29F65F3E900DBB9AFF4064DC4AB2F843ACDA8

        def der(value):
            raw = value.to_bytes(32, "big").lstrip(bytes(1))
            raw = bytes(1) + raw if raw[0] & 0x80 else raw
            return bytes([2, len(raw)]) + raw

        body = der(r) + der(s)
        signature = bytes([0x30, len(body)]) + body
        self.assertEqual(webauthn.multiply(private, webauthn.G), public)
        self.assertTrue(webauthn.verify_es256(public, b"sample", signature))
        self.assertFalse(webauthn.verify_es256(public, b"samplf", signature))


class LaunchIntegrationTests(unittest.TestCase):
    def test_launch_work_stage_accepts_only_an_approved_grant(self):
        import test_work_graph_launch as launch_tests
        from laomedo.work_graph.launch import launch_work_stage, preflight
        from laomedo.workflow_run_store import WorkflowRunStore

        corpus = json.loads(launch_tests.CORPUS.read_text(encoding="utf-8"))
        frozen = launch_tests.snapshot(corpus, "base")
        decision = preflight(frozen, frozen, launch_tests.WORK)
        with tempfile.TemporaryDirectory() as temp:
            key = FixtureAuthenticator()
            authority = ProtectedApprovalAuthority(Path(temp) / "approval.sqlite3", key.anchor())
            submitted = authority.submit(request(
                work_key=launch_tests.WORK,
                content_digest=decision["selected_content_digest"],
                graph_snapshot_id=decision["selected_graph_snapshot_id"]))
            with closing(sqlite3.connect(Path(temp) / "approval.sqlite3")) as db:
                nonce = b64url_decode(db.execute("SELECT nonce FROM requests").fetchone()[0])
            grant_id = authority.approve(submitted["request_id"], key.assert_(derive_challenge(
                submitted["request_id"], nonce, submitted["request_digest"])))
            stage = launch_tests.FakeStage()
            store = WorkflowRunStore(Path(temp) / "runs.sqlite3")

            def run(ref):
                return launch_work_stage(frozen=frozen, source_fetch=lambda _repo: frozen,
                    work_key=launch_tests.WORK, stage=stage, store=store, grant_ref=ref,
                    grant_authority=authority, resolved_config={"provider": "fake"})

            with self.assertRaisesRegex(LaunchError, "grant_invalid"):
                run("grant-never-approved")
            _record, result = run(grant_id)
            self.assertEqual((result, stage.calls), ("DONE", 1))
            self.assertEqual(store.get(stage.run_id)["status"], "completed")
            with self.assertRaisesRegex(LaunchError, "grant_invalid"):
                run(grant_id)
            self.assertEqual(stage.calls, 1)

if __name__ == "__main__":
    unittest.main()
