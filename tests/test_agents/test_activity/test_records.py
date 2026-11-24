"""Independent record projections and boundary values; internal regressions."""

import unittest
from laomedo.agents.activity.models import ActivityAttemptRecord


class ActivityRecordTests(unittest.TestCase):
    """Keep literal expected records independent of production serializers."""

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
