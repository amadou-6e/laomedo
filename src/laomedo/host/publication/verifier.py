"""Foreground credential-free verifier for active-run frozen Git handoffs.

Run independently of the credential-owning mediator. Agent requests select
neither paths nor Docker options. This worker never pushes, reads a token or
retries a consumed verification identity. Service-manager deployment and
worker-crash cleanup remain separate acceptance gates."""

from __future__ import annotations

from pathlib import Path
import json
from laomedo._paths import package_root
from laomedo.host.publication.bundle.settings import PINNED_IMAGE_ID
from laomedo.host.publication.bundle.errors import BundleStageError
from laomedo.host.publication.bundle.ownership import reconcile_orphan
from laomedo.host.publication.bundle.stage import _read_frozen
from laomedo.host.publication.bundle.stage import _run
from laomedo.host.publication.bundle.stage import verify_frozen_bundle
from laomedo.host.publication.status import _publish_status
from laomedo.host.publication.ingestion.settings import RUN_IDENTITY
from laomedo.host.publication.ingestion.errors import BundleIngestError
from laomedo.host.publication.ingestion.utils import validate_ingestion_roots
from laomedo.host.publication.ingestion.utils import write_durable_json
from laomedo.host.publication.ingestion.utils import read_run_binding
from laomedo.host.publication.ingestion.utils import is_redirected_path
import os
import secrets
import threading
import time


class BundleVerifier:
    def __init__(
        self,
        runner_state: Path,
        private_root: Path,
        *,
        agent_mount: Path,
        baseline_bundle: Path,
        baseline_sha256: str,
        verify=verify_frozen_bundle,
    ):
        self.runner_state, self.private_root = validate_ingestion_roots(
            runner_state, private_root
        )
        mounted = Path(agent_mount).resolve()
        self.baseline = Path(baseline_bundle)
        if (
            is_redirected_path(self.baseline)
            or not self.baseline.is_file()
            or self.baseline.resolve().is_relative_to(mounted)
            or self.private_root.is_relative_to(mounted)
            or mounted.is_relative_to(self.private_root)
        ):
            raise ValueError("verifier_boundary_invalid")
        if (
            not isinstance(baseline_sha256, str)
            or len(baseline_sha256) != 64
            or any(c not in "0123456789abcdef" for c in baseline_sha256)
        ):
            raise ValueError("baseline_hash_invalid")
        self.baseline_sha256 = baseline_sha256
        self.verify = verify

    def check_attempt(self, run_id: str, attempt_id: str) -> dict:
        # Trusted host roots, frozen bytes and the live record provide identity.
        # Neither the mediator capability nor provider identity enters here.
        attempt, frozen = _read_frozen(
            self.runner_state, self.private_root, run_id, attempt_id
        )
        _, before = read_run_binding(self.runner_state, run_id)
        if before.get("binding_mode") != "active":
            raise BundleStageError("verifier_run_not_active")
        # Persistent exclusive claim fences accidentally duplicated workers.
        # It is never removed: a crash cannot cause another Docker dispatch.
        with (attempt / "verifier-claim.json").open("xb") as claim:
            claim.write(
                (
                    json.dumps(
                        {"run_id": run_id, "attempt_id": attempt_id, "pid": os.getpid()}
                    )
                    + "\n"
                ).encode()
            )
            claim.flush()
            os.fsync(claim.fileno())
        try:
            result = self.verify(
                self.runner_state,
                self.private_root,
                run_id=run_id,
                attempt_id=attempt_id,
                baseline_bundle=self.baseline,
                expected_baseline_sha256=self.baseline_sha256,
                commit=frozen["advertised_commit"],
                image_id=PINNED_IMAGE_ID,
            )
        except Exception as failure:
            journal = attempt / "verification.json"
            if (
                not journal.exists()
                and not journal.with_name(journal.name + ".pending").exists()
            ):
                # Known validation rejection is pre-dispatch. Unexpected or
                # partially journaled failure must not be called a safe retry.
                result = {
                    "run_id": run_id,
                    "attempt_id": attempt_id,
                    "status": (
                        "failed" if isinstance(failure, BundleStageError) else "unknown"
                    ),
                    "error_class": type(failure).__name__,
                }
                write_durable_json(journal, result)
                return result
            raise
        try:
            _, after = read_run_binding(self.runner_state, run_id)
            unchanged = before == after
        except BundleIngestError:
            unchanged = False
        if not unchanged:
            result = {
                **result,
                "status": "unknown",
                "error_class": "run_binding_changed",
            }
            write_durable_json(attempt / "verification.json", result)
        return result

    def scan_once(self) -> list[dict]:
        results = []
        for run in self.private_root.iterdir():
            if (
                is_redirected_path(run)
                or not run.is_dir()
                or not RUN_IDENTITY.fullmatch(run.name)
            ):
                continue
            for attempt in run.iterdir():
                if (
                    is_redirected_path(attempt)
                    or not attempt.is_dir()
                    or not RUN_IDENTITY.fullmatch(attempt.name)
                ):
                    continue
                # Claimed attempts remain one-shot, but orphan lookup/cleanup
                # is independent of verification and never re-dispatches it.
                if (attempt / "container-owner.json").exists():
                    completed = False
                    try:
                        saved = json.loads((attempt / "verification.json").read_bytes())
                        cleanup = (
                            json.loads((attempt / "orphan-cleanup.json").read_bytes())
                            if (attempt / "orphan-cleanup.json").exists()
                            else {}
                        )
                        completed = (
                            saved.get("container", {}).get("cleanup_verified") is True
                            or cleanup.get("cleanup_verified") is True
                        )
                    except (OSError, ValueError, TypeError, AttributeError):
                        pass
                    if not completed:
                        reconcile_orphan(attempt, docker=_run)
                if (
                    (attempt / "verifier-claim.json").exists()
                    or (attempt / "verification.json").exists()
                    or (attempt / "verification.json.pending").exists()
                ):
                    continue
                try:
                    result = self.check_attempt(run.name, attempt.name)
                    # Do not publish paths, untrusted text or provider secrets.
                    results.append(
                        {
                            "run_id": run.name,
                            "attempt_id": attempt.name,
                            "status": result.get("status", "unknown"),
                        }
                    )
                except Exception:
                    # A not-yet-frozen attempt may become ready later. A
                    # verification.json reservation, however, is never retried.
                    continue
        return results

    def serve(self, stopping: threading.Event) -> None:
        # Host-only readiness diagnostic, not an authorization or proof that
        # a long-running scan/remote effect has stopped. A monitor must also
        # verify exact task/process ownership and freshness. No token/run
        # paths or untrusted record text are published here.
        status = {
            "instance": secrets.token_hex(16),
            "pid": os.getpid(),
            "module_root": str(package_root()),
            "started_monotonic": time.monotonic(),
            "scan_started_monotonic": None,
            "scan_completed_monotonic": None,
        }
        path = self.private_root / "service-status.json"
        try:
            while not stopping.is_set():
                status.update(phase="scanning", scan_started_monotonic=time.monotonic())
                _publish_status(path, status)
                self.scan_once()
                status.update(phase="idle", scan_completed_monotonic=time.monotonic())
                _publish_status(path, status)
                stopping.wait(0.2)
        finally:
            status.update(phase="stopped")
            _publish_status(path, status)
