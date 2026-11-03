"""Preserve serialized contracts, authority boundaries and unknown outcomes."""

from support.paths import repository_root
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from laomedo.host.mediation.models import AuthorizedLeaseScope, MediationServiceRecord


class MediationRecordTests(unittest.TestCase):
    def test_unconnected_approval_round_trip_preserves_optional_base_and_null_connection(
        self,
    ):
        from laomedo.host.mediation.authority import RunGrantAuthority

        for operations in ({"actions_read"}, {"git_fetch"}, {"pr_update"}):
            with self.subTest(operations=operations), TemporaryDirectory() as temporary:
                authority = RunGrantAuthority(Path(temporary) / "authority.sqlite")
                targets = {17: "develop"}
                reference = authority.approve(
                    invocation_id="invocation",
                    repository="owner/repo",
                    branch="work",
                    operations=operations,
                    reviewed_by="reviewer",
                    target_prs=targets,
                    base_branch="develop",
                )
                request = authority.bind_run(reference, "run")
                expected = dict(
                    invocation_id="invocation", repository="owner/repo", branch="work"
                )
                if operations != {"actions_read"}:
                    expected["base_branch"] = "develop"
                self.assertEqual(request, expected)
                lease = {"run_id": "run", "token": "private-lease"}
                scope = authority.authorize_lease(lease, request)
                self.assertEqual(
                    scope,
                    {
                        **expected,
                        "operations": operations,
                        "approval_identity": "reviewer",
                        "connection_id": None,
                        "connection_generation": None,
                        "target_prs": targets,
                    },
                )
                self.assertIn("connection_id", scope)
                self.assertIn("connection_generation", scope)
                self.assertIsNone(scope["connection_id"])
                self.assertIsNone(scope["connection_generation"])
                self.assertIs(type(scope["operations"]), set)
                self.assertIs(type(next(iter(scope["target_prs"]))), int)
                self.assertEqual(authority.authorize_lease(lease, request), scope)
                self.assertIsNone(
                    authority.authorize_lease(
                        {**lease, "token": "other-lease"}, request
                    )
                )
                self.assertIsNone(
                    authority.authorize_lease(
                        lease, {**request, "base_branch": "other"}
                    )
                )

    def test_mediation_metadata_preserves_omission_and_python_authority_types(self):
        values = dict(
            pid=12,
            port=8000,
            instance="instance",
            started_at=10,
            connection_id="connection",
            generation=2,
            repository="owner/repo",
        )
        self.assertEqual(MediationServiceRecord(**values).to_record(), values)
        self.assertEqual(
            MediationServiceRecord(**values, module_root=None).to_record(),
            {**values, "module_root": None},
        )
        scope = dict(
            invocation_id="invocation",
            repository="owner/repo",
            branch=None,
            operations={"pr_read"},
            approval_identity="approval",
            connection_id="connection",
            connection_generation=2,
            target_prs={3: "develop"},
        )
        result = AuthorizedLeaseScope(**scope).to_record()
        self.assertEqual(result, scope)
        self.assertIs(type(result["operations"]), set)
        self.assertIs(type(next(iter(result["target_prs"]))), int)
