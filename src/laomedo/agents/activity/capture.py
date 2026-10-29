"""Bind dispatch to retained activity and close each observed attempt."""

from __future__ import annotations

from pathlib import Path
from urllib.request import ProxyHandler
from urllib.request import Request
from urllib.request import build_opener
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
        self.opener = build_opener(ProxyHandler({}))
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

    def feed(self, run_id, after, otel_after):
        url = f"{self.base}/v1/runs/{run_id}/events?attempt={self.attempt_id}&after={after}&otel_after={otel_after}&limit=200"
        with self.opener.open(
            Request(url, headers={"Authorization": "Bearer " + self.token}), timeout=10
        ) as response:
            value = json.load(response)
        if value.get("run_id") != run_id:
            raise ValueError("activity_runner_identity_mismatch")
        if (
            value.get("accepted")
            and value.get("attempt", {}).get("id") != self.attempt_id
        ):
            raise ValueError("activity_attempt_identity_mismatch")
        return value

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
        store = self.capture.store
        invocation = self.capture.invocation_id
        after = otel_after = 0
        deadline = time.monotonic() + self.timeout
        failures = 0
        terminal_native = False
        try:
            while time.monotonic() < deadline:
                if self.refused.is_set():
                    return
                try:
                    page = self.feed(run_id, after, otel_after)
                    failures = 0
                except Exception:
                    failures += 1
                    if failures >= 3:
                        raise
                    time.sleep(0.3)
                    continue
                if not page.get("accepted"):
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
                attempt = page["attempt"]
                if not self.accepted:
                    if not store.claim_attempt(invocation, run_id, self.attempt_id):
                        store.finish(
                            invocation,
                            "completed",
                            reason="existing_attempt_reference_no_new_usage",
                        )
                        return
                    self.accepted = True
                    after = attempt["native_start"]
                    otel_after = attempt["otel_start"]
                    store.append(
                        invocation,
                        {
                            "method": "capture/usageBaseline",
                            "threads": attempt["usage_baseline"],
                            "fresh_thread": attempt.get("fresh_thread") is True,
                        },
                    )
                store.bind(
                    invocation,
                    run_id,
                    native_session=page.get("thread_id"),
                    model=page.get("model"),
                )
                for item in page["events"]:
                    store.append(
                        invocation,
                        {
                            "method": "native/receipt",
                            "received_at": item["received_at"],
                            "event": item["event"],
                        },
                        source="native",
                        cursor=item["cursor"],
                    )
                    terminal_native = (
                        terminal_native
                        or item["event"].get("method") == "turn/completed"
                    )
                after = page["next_after"]
                telemetry = page.get("telemetry", {})
                for item in telemetry.get("events", []):
                    store.append(
                        invocation,
                        {
                            "method": "otel/receipt",
                            "received_at": item["received_at"],
                            "event": item["event"],
                        },
                        source="otel",
                        cursor=item["cursor"],
                    )
                otel_after = telemetry.get("next_after", otel_after)
                if (
                    attempt.get("native_end") is not None
                    and after >= attempt["native_end"]
                    and otel_after >= attempt["otel_end"]
                ):
                    status = attempt["status"]
                    if (
                        getattr(getattr(self, "component", None), "name", None)
                        == "LaomedoOpenCodeAgent"
                    ):
                        terminal_native = attempt.get(
                            "capture_complete", attempt.get("native_stream_complete")
                        ) is True
                    if status in {"completed", "failed", "cancelled", "timeout"}:
                        store.finish(
                            invocation,
                            "timed_out" if status == "timeout" else status,
                            complete=terminal_native
                            and not attempt.get("capture_error"),
                            reason=attempt.get("capture_error")
                            or (
                                None
                                if terminal_native
                                else (
                                    "native_message_snapshot_only"
                                    if getattr(
                                        getattr(self, "component", None), "name", None
                                    )
                                    == "LaomedoOpenCodeAgent"
                                    else "native_terminal_event_not_observed"
                                )
                            ),
                            ended_at=attempt["ended_at"],
                        )
                        return
                if not page.get("has_more") and not telemetry.get("has_more"):
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
