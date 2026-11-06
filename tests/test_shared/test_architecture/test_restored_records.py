"""Canonical Shared records remain described, class-only and hidden on failure."""

import ast
import importlib
from pathlib import Path
import unittest
from pydantic import BaseModel


class SharedRecordStructureTests(unittest.TestCase):
    def test_shared_records_have_one_documented_model_owner(self):
        required = {
            "host.credentials.siwc.models": {
                "OAuthAuthorizationRequest",
                "OAuthAttempt",
                "OAuthCodeExchange",
                "OAuthAccount",
            },
            "host.mediation.models": {"MediationServiceRecord", "AuthorizedLeaseScope"},
            "host.publication.bundle.models": {
                "ContainerStageRecord",
                "BundleVerificationRecord",
            },
            "host.publication.handoff.models": {"PullRequestPublicationRequest"},
            "host.publication.verified.models": {
                "VerifiedStage",
                "VerifiedStageIdentity",
            },
            "work_graph.models": {
                "RelevantWorkContent",
                "WorkSnapshot",
                "WorkOverride",
                "WorkLaunchBinding",
                "WorkGrantLimits",
                "WorkLaunchGrant",
                "WorkGrantReference",
                "WorkLaunchResult",
            },
            "git.models": {
                "GitCommand",
                "GitCredential",
                "GitExecutionContext",
                "GitExecutionBudget",
            },
        }
        for name, expected in required.items():
            module = importlib.import_module("laomedo." + name)
            tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
            self.assertFalse(
                any(
                    isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    for node in tree.body
                ),
                name,
            )
            defined = {
                value.__name__
                for value in vars(module).values()
                if isinstance(value, type)
                and issubclass(value, BaseModel)
                and value.__module__ == module.__name__
            }
            self.assertTrue(
                expected <= defined,
                f"{name} must define the expected canonical models: {sorted(expected - defined)}",
            )
            self.assertTrue(
                defined, f"{name} must not become an empty or forwarding module"
            )
            for value in vars(module).values():
                if (
                    isinstance(value, type)
                    and issubclass(value, BaseModel)
                    and value.__module__ == module.__name__
                ):
                    # Existing WorkItem/Dependency/GraphSnapshot fields retain their established contract;
                    # the newly restored records all describe their externally read fields.
                    if value.__name__ in {"WorkItem", "Dependency", "GraphSnapshot"}:
                        continue
                    with self.subTest(model=value.__name__):
                        self.assertTrue(
                            all(
                                field.description
                                for field in value.model_fields.values()
                            )
                        )
