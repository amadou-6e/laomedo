"""Independent handoff and fresh-request canonical hash preimages."""

import json
from pathlib import Path
import unittest
from unittest.mock import patch
from laomedo.agents.orchestration.utils import envelope
from laomedo.agents.interface.bridge import HttpAgentBridge


class RequestRecordTests(unittest.TestCase):
    def test_handoff_and_request_hash_preimages_match_baseline(self):
        cases = json.loads(
            (Path(__file__).parent / "data/request-records.json").read_text(
                encoding="utf-8"
            )
        )
        with patch(
            "laomedo.agents.orchestration.utils.uuid4",
            return_value="22222222-2222-4222-8222-222222222222",
        ):
            result = envelope(
                None,
                {"provider": "codex", "model": "model", "effort": "low"},
                "Read only.",
                skills=[],
            )
        self.assertEqual(result, cases["handoff"])
        request, digest = HttpAgentBridge.fresh_request(result, "request-id")
        self.assertEqual(request, cases["request"]["payload"])
        self.assertEqual(digest, cases["request"]["digest"])
        self.assertEqual(
            json.dumps(
                {k: v for k, v in request.items() if k != "request_id"},
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ),
            cases["request"]["preimage"],
        )
