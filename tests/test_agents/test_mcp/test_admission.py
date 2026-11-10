"""Current request identity and frozen external-grant admission contracts."""

from pathlib import Path
import json
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from pydantic import ValidationError

from laomedo.agents.mcp.client import McpAccess
from laomedo.agents.mcp.models import McpManifest, McpTool
from laomedo.agents.mcp.settings import McpSettings
from laomedo.agents.errors import RunnerError
from test_agents.test_runtime.models import RunnerCase
from support.paths import repository_root
from laomedo.agents.mcp.settings import MCP_ERROR_CODES


class McpAdmissionTests(unittest.TestCase):
    """Protect semantic identity, paired admission and absence of persisted secrets."""

    def setUp(self):
        """Prepare a non-secret exact tool grant independent of provider behavior."""
        self.tool = McpTool(
            server="sample",
            upstream_name="echo",
            display_name="Echo",
            description="Echo a supplied message.",
            input_schema={"type": "object"},
        )
        self.manifest = McpManifest(tools=(self.tool,))

    def test_manifest_is_order_independent_and_rejects_duplicate_identity(self):
        """Different list ordering is not a new grant, and aliases cannot duplicate tools."""
        other = self.tool.model_copy(update={"upstream_name": "other"})
        left = McpManifest(tools=(self.tool, other))
        right = McpManifest(tools=(other, self.tool))
        self.assertEqual(left.model_dump(), right.model_dump())
        self.assertEqual(left.digest(), right.digest())
        with self.assertRaises(ValidationError):
            McpManifest(
                tools=(
                    self.tool,
                    self.tool.model_copy(update={"display_name": "Alias"}),
                )
            )

    def test_semantic_identity_excludes_only_transient_registration(self):
        """A new capability can represent the same request without masking tool drift."""
        request = {
            "task": "read",
            "mcp_manifest": self.manifest.model_dump(mode="json"),
            "mcp_registration": str(uuid4()),
        }
        changed = {**request, "mcp_registration": str(uuid4())}
        self.assertEqual(
            McpAccess.semantic_request(request), McpAccess.semantic_request(changed)
        )
        changed["mcp_manifest"] = McpManifest(
            tools=(self.tool.model_copy(update={"upstream_name": "other"}),)
        ).model_dump(mode="json")
        self.assertNotEqual(
            McpAccess.semantic_request(request), McpAccess.semantic_request(changed)
        )

    def test_wildcard_and_public_bind_addresses_are_refused(self):
        """Never turn a Docker reachability failure into all-interface exposure."""
        for address in ("0.0.0.0", "::", "8.8.8.8"):
            with self.subTest(address=address), self.assertRaises(ValidationError):
                McpSettings(bind=address)

    def test_mcp_failures_have_recovery_without_automatic_call_replay(self):
        """Every forwarded failure has a useful explanation at the graph boundary."""
        catalogue = json.loads(
            (
                repository_root()
                / "frontend/langflow-skill-viewer/node-error-catalog.json"
            ).read_text(encoding="utf-8")
        )
        for code in MCP_ERROR_CODES:
            with self.subTest(code=code):
                self.assertTrue(catalogue[code]["title"].strip())
                self.assertTrue(catalogue[code]["description"].strip())
                self.assertTrue(catalogue[code]["recovery"].strip())
        self.assertIn("1.12.3", catalogue["mcp_native_version_unsupported"]["recovery"])
        self.assertNotIn("effects", catalogue["mcp_manifest_invalid"]["description"])
        self.assertIn(
            "do not automatically repeat",
            catalogue["mcp_call_outcome_unknown"]["recovery"],
        )

    def test_preparation_persists_manifest_and_never_capability(self):
        """Only the tool grant enters the actual prepared run record."""
        case = RunnerCase.create()
        self.addCleanup(case.close)
        access = Mock()
        access.token = "PRIVATE-CAPABILITY-MUST-NOT-PERSIST"
        request = {
            **case.request(),
            "mcp_registration": str(uuid4()),
            "mcp_manifest": self.manifest.model_dump(mode="json"),
        }
        with patch("laomedo.agents.agents.base.agent.McpAccess", return_value=access):
            record = case.runner._prepare(request)
        self.addCleanup(case.runner.release_mcp, record["run_id"])
        access.claim.assert_called_once_with(record["run_id"])
        self.assertEqual(record["mcp_manifest"], self.manifest.model_dump(mode="json"))
        retained = (
            case.runner.state / "runs" / record["run_id"] / "record.json"
        ).read_text()
        self.assertNotIn(access.token, retained)
        self.assertNotIn("mcp_registration", record)

    def test_missing_registration_is_refused_before_preparation(self):
        """Unpaired tool metadata cannot produce an admitted workspace or run."""
        case = RunnerCase.create()
        self.addCleanup(case.close)
        request = {
            **case.request(),
            "mcp_manifest": self.manifest.model_dump(mode="json"),
        }
        with self.assertRaisesRegex(RunnerError, "mcp_registration_required"):
            case.runner._prepare(request)
        self.assertEqual(list((case.runner.state / "runs").iterdir()), [])

    def test_attempt_cleanup_cannot_release_a_replacement_grant(self):
        """Late cleanup from an older handler only owns its exact admitted access."""
        case = RunnerCase.create()
        self.addCleanup(case.close)
        run_id = str(uuid4())
        old = Mock()
        current = Mock()
        case.runner._mcp_access[run_id] = current
        case.runner.release_mcp(run_id, expected=old)
        self.assertIs(case.runner.mcp_access(run_id), current)
        current.close.assert_not_called()
        case.runner.release_mcp(run_id, expected=current)
        current.close.assert_called_once()
