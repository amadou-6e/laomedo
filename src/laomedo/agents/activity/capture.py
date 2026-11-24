"""Bind dispatch to retained activity and close each observed attempt."""

from __future__ import annotations

from laomedo.agents.activity.models import ActivityPage
from pathlib import Path
from urllib.request import ProxyHandler
from urllib.request import Request
from urllib.request import build_opener
from laomedo.host.http import NoRedirect
from uuid import UUID
import json
from laomedo.agents.activity.utils import capture_for
import threading
import time


class ActivityCapture:
    def __init__(self, component):
        self.capture = capture_for(component)
        self.done = threading.Event()
        self.refused = threading.Event()
        self.started = False
        self.accepted = False
        self.attempt_id = None
        self.outcome = None
        self.component = component
        self.base = str(component.runner_url).rstrip("/")
        self.timeout = max(30, int(component.timeout_seconds) + 30)
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        if self.capture:
            try:
                path = component._runner_token_file_path()
                self.token = Path(path).read_text().strip()
                if not self.token:
                    raise ValueError("activity_runner_token_missing")
            except Exception:
                self.capture.store.finish(
                    self.capture.invocation_id,
                    "failed",
                    reason="activity_runner_auth_unavailable",
                )
                raise

    def feed(self, run_id, after):
        """Read the provider's common Activity page, not its private source feeds."""
        url = f"{self.base}/v1/runs/{run_id}/activity?attempt={self.attempt_id}&after={after}&limit=200"
        with self.opener.open(
            Request(url, headers={"Authorization": "Bearer " + self.token}), timeout=10
        ) as response:
            page = ActivityPage.model_validate_json(response.read())
        if page.run_id != run_id:
            raise ValueError("activity_runner_identity_mismatch")
        if page.attempt_id != self.attempt_id:
            raise ValueError("activity_attempt_identity_mismatch")
        return page

    def bind(self, run_id, attempt_id=None):
        if not self.capture or self.started:
            return
        if not isinstance(attempt_id, str) or str(UUID(attempt_id)) != attempt_id:
            raise ValueError("activity_attempt_identity_required")
        self.attempt_id = attempt_id
        self.capture.store.bind(self.capture.invocation_id, run_id)
        self.started = True
        threading.Thread(
            target=self.observe,
            args=(run_id,),
            daemon=True,
            name="laomedo-activity-observer",
        ).start()

    def observe(self, run_id):
        """Retain common records and display snapshots without provider interpretation."""
        store = self.capture.store
        invocation = self.capture.invocation_id
        after = 0
        deadline = time.monotonic() + self.timeout
        failures = 0
        try:
            while time.monotonic() < deadline:
                if self.refused.is_set():
                    return
                try:
                    page = self.feed(run_id, after)
                    failures = 0
                except Exception:
                    failures += 1
                    if failures >= 3:
                        raise
                    time.sleep(0.3)
                    continue
                if not page.available:
                    if self.done.is_set() and self.outcome in {
                        "completed",
                        "failed",
                        "cancelled",
                        "timeout",
                    }:
                        store.finish(
                            invocation, "failed", reason="dispatch_not_accepted"
                        )
                        return
                    time.sleep(0.25)
                    continue
                if not self.accepted:
                    if not store.claim_attempt(invocation, run_id, self.attempt_id):
                        store.finish(
                            invocation,
                            "completed",
                            reason="existing_attempt_reference_no_new_usage",
                        )
                        return
                    self.accepted = True
                store.bind(
                    invocation, run_id, native_session=page.thread_id, model=page.model
                )
                source = run_id + ":" + self.attempt_id
                if page.projection is not None:
                    store.append(
                        invocation,
                        {
                            "method": "activity/projection",
                            "projection": page.projection.to_payload(),
                            "revision": page.projection_revision,
                            "run_id": run_id,
                            "attempt_id": self.attempt_id,
                        },
                        source="projection:" + source,
                        cursor=page.projection_revision,
                    )
                for record in page.records:
                    store.append(
                        invocation,
                        {
                            "method": "activity/record",
                            "record": record.model_dump(mode="json"),
                        },
                        source="normalized:" + source,
                        cursor=record.sequence,
                    )
                if page.next_after < after:
                    raise ValueError("invalid_activity_cursor")
                after = page.next_after
                if page.closed and not page.has_more:
                    status = (
                        "timed_out"
                        if page.status in {"timeout", "timed_out"}
                        else (
                            page.status
                            if page.status in {"completed", "failed", "cancelled"}
                            else "failed"
                        )
                    )
                    store.finish(
                        invocation,
                        status,
                        complete=page.complete is True,
                        reason=page.reason
                        or (
                            "remote_outcome_unknown"
                            if page.status == "unknown"
                            else None
                        ),
                        ended_at=page.ended_at,
                    )
                    return
                if not page.has_more:
                    time.sleep(0.25)
            store.finish(
                invocation,
                "timed_out",
                reason="observation_deadline_remote_outcome_unknown",
            )
        except Exception:
            store.finish(
                invocation,
                "failed",
                reason="activity_capture_interrupted_remote_outcome_unknown",
            )

    def dispatched(self, *, result=None, refused=False):
        self.outcome = (result or {}).get("status")
        if refused:
            self.refused.set()
            if self.capture:
                self.capture.store.finish(
                    self.capture.invocation_id, "failed", reason="dispatch_refused"
                )
        self.done.set()
        if self.capture and not self.started:
            self.capture.store.finish(
                self.capture.invocation_id, "failed", reason="dispatch_not_bound"
            )
