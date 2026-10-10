"""Unexecuted live-controller preflight controls; no HTTP request or process."""
from unittest.mock import patch
import pytest
from experiments.exp104 import native_managed_probe as probe


def test_changed_target_stops_before_branch_reads():
    with patch.object(probe, "api", side_effect=[{"id": 999}, {}, {}]) as api:
        with pytest.raises(ValueError, match="preflight_target_mismatch"):
            probe.preflight("synthetic-secret")
        assert api.call_count == 3


def test_existing_fresh_branch_is_refused_without_write():
    with patch.object(probe, "api", side_effect=[
            {"id": 1408647759, "default_branch": "main", "permissions": {"push": True}},
            {"object": {"sha": probe.BASELINE}}, {"login": "ga84jog"}, {}]) as api:
        with pytest.raises(ValueError, match="preflight_branch_exists"):
            probe.preflight("synthetic-secret")
        assert api.call_count == 4
