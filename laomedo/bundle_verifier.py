"""Foreground credential-free verifier for active-run frozen Git handoffs.

Run independently of the credential-owning mediator. Agent requests select
neither paths nor Docker options. This worker never pushes, reads a token or
retries a consumed verification identity. Service-manager deployment and
worker-crash cleanup remain separate acceptance gates.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import threading

from .bundle_ingest import (_bound_roots, _record, _redirected, _durable_json,
                            BundleIngestError, _IDENTITY)
from .bundle_stage import (verify_frozen_bundle, _read_frozen,
                           PINNED_IMAGE_ID, BundleStageError)


class BundleVerifier:
    def __init__(self, runner_state: Path, private_root: Path, *,
                 agent_mount: Path, baseline_bundle: Path,
                 baseline_sha256: str, verify=verify_frozen_bundle):
        self.runner_state, self.private_root = _bound_roots(runner_state, private_root)
        mounted = Path(agent_mount).resolve()
        self.baseline = Path(baseline_bundle)
        if (_redirected(self.baseline) or not self.baseline.is_file() or
                self.baseline.resolve().is_relative_to(mounted) or
                self.private_root.is_relative_to(mounted) or
                mounted.is_relative_to(self.private_root)):
            raise ValueError("verifier_boundary_invalid")
        if (not isinstance(baseline_sha256, str) or len(baseline_sha256) != 64 or
                any(c not in "0123456789abcdef" for c in baseline_sha256)):
            raise ValueError("baseline_hash_invalid")
        self.baseline_sha256 = baseline_sha256
        self.verify = verify

    def check_attempt(self, run_id: str, attempt_id: str) -> dict:
        # Trusted host roots, frozen bytes and the live record provide identity.
        # Neither the mediator capability nor provider identity enters here.
        attempt, frozen = _read_frozen(self.runner_state, self.private_root,
                                       run_id, attempt_id)
        _, before = _record(self.runner_state, run_id)
        if before.get("binding_mode") != "active":
            raise BundleStageError("verifier_run_not_active")
        # Persistent exclusive claim fences accidentally duplicated workers.
        # It is never removed: a crash cannot cause another Docker dispatch.
        with (attempt / "verifier-claim.json").open("xb") as claim:
            claim.write((json.dumps({"run_id": run_id, "attempt_id": attempt_id,
                                     "pid": os.getpid()}) + "\n").encode())
            claim.flush()
            os.fsync(claim.fileno())
        try:
            result = self.verify(self.runner_state, self.private_root,
                run_id=run_id, attempt_id=attempt_id,
                baseline_bundle=self.baseline,
                expected_baseline_sha256=self.baseline_sha256,
                commit=frozen["advertised_commit"], image_id=PINNED_IMAGE_ID)
        except Exception as failure:
            journal = attempt / "verification.json"
            if not journal.exists() and not journal.with_name(journal.name + ".pending").exists():
                # Known validation rejection is pre-dispatch. Unexpected or
                # partially journaled failure must not be called a safe retry.
                result = {"run_id": run_id, "attempt_id": attempt_id,
                          "status": "failed" if isinstance(failure, BundleStageError) else "unknown",
                          "error_class": type(failure).__name__}
                _durable_json(journal, result)
                return result
            raise
        try:
            _, after = _record(self.runner_state, run_id)
            unchanged = before == after
        except BundleIngestError:
            unchanged = False
        if not unchanged:
            result = {**result, "status": "unknown", "error_class": "run_binding_changed"}
            _durable_json(attempt / "verification.json", result)
        return result

    def scan_once(self) -> list[dict]:
        results = []
        for run in self.private_root.iterdir():
            if _redirected(run) or not run.is_dir() or not _IDENTITY.fullmatch(run.name):
                continue
            for attempt in run.iterdir():
                if (_redirected(attempt) or not attempt.is_dir() or
                        not _IDENTITY.fullmatch(attempt.name) or
                        (attempt / "verifier-claim.json").exists() or
                        (attempt / "verification.json").exists() or
                        (attempt / "verification.json.pending").exists()):
                    continue
                try:
                    result = self.check_attempt(run.name, attempt.name)
                    # Do not publish paths, untrusted text or provider secrets.
                    results.append({"run_id": run.name, "attempt_id": attempt.name,
                                    "status": result.get("status", "unknown")})
                except Exception:
                    # A not-yet-frozen attempt may become ready later. A
                    # verification.json reservation, however, is never retried.
                    continue
        return results

    def serve(self, stopping: threading.Event) -> None:
        while not stopping.is_set():
            self.scan_once()
            stopping.wait(.2)


def main():
    # Explicitly refuse ambient provider overrides rather than falling back.
    if any(key in os.environ for key in
           ("GH_TOKEN", "GITHUB_TOKEN", "GH_LAOMEDO", "GH", "GIT_ASKPASS")):
        raise ValueError("verifier_credential_environment_denied")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-state", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--agent-mount", type=Path, required=True)
    parser.add_argument("--baseline-bundle", type=Path, required=True)
    parser.add_argument("--baseline-sha256", required=True)
    args = parser.parse_args()
    worker = BundleVerifier(**vars(args))
    try:
        worker.serve(threading.Event())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
