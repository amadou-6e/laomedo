"""Current target-value invariants; no provider execution or historical migration."""

from pathlib import Path
import unittest
from unittest.mock import Mock

from pydantic import SecretStr, ValidationError

from laomedo.agents.agents.base.models.runtime import (
    CleanupObservation,
    NamedCleanup,
    ResourcePlan,
    ContainerStep,
    OwnedResourceStep,
    RuntimeCleanupReport,
)
from laomedo.agents.agents.base.models.credentials import (
    CredentialAdmission,
    CredentialBinding,
    CredentialMaterial,
)
from laomedo.agents.agents.base.models.journal import NativeSessionEntry
from laomedo.agents.agents.base.models.invocation import (
    SettlementUpdates,
    InvocationRequest,
    InvocationContext,
    InvocationResult,
    SettlementView,
)
from laomedo.agents.agents.base import BasePostFreezeSettlement


class TargetValueTests(unittest.TestCase):
    """Guard dependency admission and facts that must never fabricate cleanup."""

    def test_unknown_cleanup_in_any_named_resource_prevents_confirmation(self):
        report = RuntimeCleanupReport(
            controller=CleanupObservation(confirmed=True, scope="controller"),
            resources=(
                NamedCleanup(
                    resource_id="workers",
                    observation=CleanupObservation(confirmed=None, scope="workers"),
                ),
            ),
        )
        self.assertFalse(report.confirmed)
        self.assertFalse(
            RuntimeCleanupReport(
                controller=CleanupObservation(confirmed=True, scope="controller"),
                resources=(),
                code="container_termination_unverified",
            ).confirmed
        )

    def test_invalid_dependencies_are_rejected_without_invoking_builders(self):
        build = Mock()
        for steps in (
            (
                ContainerStep(
                    controller=True,
                    id="controller",
                    phase="launch",
                    depends_on=("missing",),
                    build=build,
                ),
            ),
            (
                ContainerStep(
                    controller=True, id="controller", phase="launch", build=build
                ),
                ContainerStep(
                    controller=True, id="controller", phase="launch", build=build
                ),
            ),
            (
                ContainerStep(
                    controller=True, id="controller", phase="launch", build=build
                ),
                OwnedResourceStep(id="worker", phase="prepare", build=build),
            ),
        ):
            with self.subTest(steps=[step.id for step in steps]):
                with self.assertRaises(ValidationError):
                    ResourcePlan(steps=steps)
        build.assert_not_called()

    def test_admitted_plan_keeps_native_builders_out_of_serialized_values(self):
        build = Mock()
        plan = ResourcePlan(
            steps=(
                OwnedResourceStep(id="worker", phase="prepare", build=build),
                ContainerStep(
                    controller=True,
                    id="controller",
                    phase="launch",
                    depends_on=("worker",),
                    build=build,
                ),
            )
        )
        self.assertNotIn("build", plan.model_dump()["steps"][0])
        self.assertNotIn("Mock", repr(plan))
        build.assert_not_called()

    def test_admission_never_serializes_or_represents_launch_material(self):
        binding = CredentialBinding(
            credential_mode="native", credential_ref=None, auth_outcome="valid"
        )
        admission = CredentialAdmission(
            binding=binding,
            material=CredentialMaterial(
                binding=binding, token=SecretStr("private-token")
            ),
        )
        self.assertNotIn("material", admission.model_dump())
        self.assertNotIn("private-token", admission.model_dump_json())
        self.assertNotIn("private-token", repr(admission))

    def test_validation_errors_hide_native_record_and_task_content(self):
        try:
            InvocationContext(
                run_id="r",
                attempt_id="a",
                workspace=123,
                evidence=123,
                record={"answer": "private-answer"},
            )
        except ValidationError as error:
            self.assertNotIn("private-answer", str(error))
            self.assertNotIn("input_value", str(error))
        else:
            self.fail("Invalid host paths were admitted")

    def test_invocation_request_preserves_host_identity_and_fresh_resume_binding(self):
        """Host identity stays serializable while native conversation binding is explicit."""
        context = InvocationContext(
            run_id="host-run",
            attempt_id="admitted-execution",
            workspace=Path("workspace"),
            evidence=Path("evidence"),
            record={"provider": "codex"},
        )
        for resume, native_session in ((False, None), (True, "native-conversation")):
            with self.subTest(resume=resume):
                request = InvocationRequest(
                    context=context,
                    task="Inspect the workspace",
                    model="selected-model",
                    effort=None,
                    resume=resume,
                    native_session=native_session,
                )
                self.assertEqual(
                    request.model_dump(mode="json")["context"],
                    {
                        "run_id": "host-run",
                        "attempt_id": "admitted-execution",
                        "workspace": "workspace",
                        "evidence": "evidence",
                        "record": {"provider": "codex"},
                    },
                )
        for resume, native_session in ((True, None), (False, "native-conversation")):
            with self.subTest(resume=resume, invalid_binding=native_session):
                with self.assertRaisesRegex(
                    ValidationError, "attempt_native_binding_mismatch"
                ):
                    InvocationRequest(
                        context=context,
                        task="Inspect the workspace",
                        model="selected-model",
                        effort=None,
                        resume=resume,
                        native_session=native_session,
                    )

    def test_native_journal_and_settlement_fields_cannot_override_shared_state(self):
        with self.assertRaises(ValidationError):
            NativeSessionEntry(
                attempt_id="a",
                native_session="s",
                communication_protocol="acp.v1",
                extensions={"status": "completed"},
            )
        with self.assertRaises(ValidationError):
            SettlementUpdates(status="completed")
        with self.assertRaises(ValidationError):
            SettlementUpdates(evidence={"cancel_confirmed": True})

    def test_uncertain_outcomes_retain_public_category_and_surviving_settlement(self):
        settlement = Mock(spec=BasePostFreezeSettlement)
        for status in ("unknown", "timeout", "interrupted", "cancelled"):
            outcome = InvocationResult(
                status=status,
                native_session=None,
                turns=(),
                error_category="existing_native_category",
                cleanup=RuntimeCleanupReport(controller=None, resources=()),
                settlement=settlement,
            )
            self.assertIs(outcome.settlement, settlement)
            self.assertEqual(outcome.error_category, "existing_native_category")
            self.assertNotIn("settlement", outcome.model_dump())

    def test_settlement_view_does_not_share_mutable_agent_record(self):
        record = {"publication_handoff": {"phase": "registered"}}
        view = SettlementView(record=record)
        view.record["publication_handoff"]["phase"] = "validation_pending"
        self.assertEqual(record["publication_handoff"]["phase"], "registered")

    def test_controller_and_monitor_are_admitted_before_builders_run(self):
        build = Mock()
        with self.assertRaises(ValidationError):
            ResourcePlan(
                steps=(OwnedResourceStep(id="broker", phase="prepare", build=build),)
            )
        with self.assertRaises(ValidationError):
            ResourcePlan(
                steps=(
                    ContainerStep(
                        id="worker", phase="prepare", build=build, stop_when=Mock()
                    ),
                    ContainerStep(
                        id="controller", phase="launch", controller=True, build=build
                    ),
                )
            )
        build.assert_not_called()
