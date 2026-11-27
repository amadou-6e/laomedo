"""Independent record projections and boundary values; internal regressions."""

import unittest
from laomedo.agents.agents.opencode.activity.models import OpenCodeTokenUsage
from laomedo.agents.agents.opencode.models import OpenCodeRuntimeIdentity


class OpenCodeRecordTests(unittest.TestCase):
    """Keep literal expected records independent of production serializers."""

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
