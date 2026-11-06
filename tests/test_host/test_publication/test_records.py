"""Preserve serialized contracts, authority boundaries and unknown outcomes."""

from support.paths import repository_root
import json
import unittest
from laomedo.host.publication.bundle.models import (
    BundleVerificationRecord,
    ContainerStageRecord,
)
from laomedo.host.publication.handoff.models import PullRequestPublicationRequest
from laomedo.host.publication.verified.models import (
    VerifiedStage,
    VerifiedStageIdentity,
)


class PublicationRecordTests(unittest.TestCase):
    def test_verified_stage_active_and_frozen_hash_preimages_match_old_writer(self):
        cases = json.loads(
            (
                repository_root()
                / "tests/test_host/test_publication/fixtures/verified-stage.json"
            ).read_text(encoding="utf-8")
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
