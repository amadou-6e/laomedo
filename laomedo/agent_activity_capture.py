"""Read-only observation of a validated original-runner dispatch."""
import json
import os
from pathlib import Path
import threading
import time
from urllib.request import Request, build_opener, ProxyHandler

from .agent_activity import capture_for, now


class RunnerCapture:
    def __init__(self, component):
        self.capture = capture_for(component)
        self.done = threading.Event()
        self.started = False
        self.run_id = None
        self.boundary = None
        self.boundary_status = None
        self.boundary_time = None
        self.observer = None
        self.after = 0
        self.origin = 0
        self.otel_after = 0
        self.component = component
        self.base = str(component.runner_url).rstrip('/')
        self.timeout = max(30, int(component.timeout_seconds) + 30)
        self.opener = build_opener(ProxyHandler({}))
        if self.capture:
            # The bridge token is never sent to the runner's independent API.
            path = os.environ.get('LAOMEDO_RUNNER_TOKEN_FILE', '/run/secrets/laomedo-runner-token')
            try:
                self.token = Path(path).read_text().strip()
                if not self.token:
                    raise ValueError('activity_runner_token_missing')
            except Exception:
                self.capture[0].finish(self.capture[1], 'failed', reason='activity_runner_auth_unavailable')
                raise

    def feed(self, run_id, *, tail=False):
        url = f'{self.base}/v1/runs/{run_id}/events?after={self.after}&from={self.origin}&otel_after={self.otel_after}&limit=200&tail={int(tail)}'
        with self.opener.open(Request(url, headers={'Authorization':'Bearer '+self.token}), timeout=10) as response:
            value = json.load(response)
        if value.get('run_id') != run_id:
            raise ValueError('activity_runner_identity_mismatch')
        return value

    def prepare_resume(self, run_id):
        if self.capture:
            page = self.feed(run_id, tail=True)
            self.after = page['next_after']
            self.origin = self.after
            self.otel_after = page.get('telemetry',{}).get('next_after',0)
            self.capture[0].append(self.capture[1], {'method':'capture/usageBaseline',
                'threads':page.get('usage_baseline',{})})
            self.bind(run_id)

    def bind(self, run_id):
        if not self.capture or self.started:
            return
        self.capture[0].bind(self.capture[1], run_id)
        self.run_id = run_id
        self.started = True
        self.observer=threading.Thread(target=self.observe, args=(run_id,), daemon=True,
                                      name='laomedo-activity-observer')
        self.observer.start()

    def observe(self, run_id):
        store, invocation = self.capture
        deadline = time.monotonic() + self.timeout
        failures = 0
        observed = False
        terminal_native = False
        try:
            while time.monotonic() < deadline:
                try:
                    page = self.feed(run_id)
                    failures = 0
                except Exception:
                    failures += 1
                    if failures >= 3:
                        raise
                    time.sleep(.3)
                    continue
                store.bind(invocation, run_id, native_session=page.get('thread_id'), model=page.get('model'))
                closed=page.get('closed_boundary')
                if closed:
                    self.boundary_status=closed['status']
                    self.boundary_time=closed['ended_at']
                    self.boundary=(closed['native_end'],closed['otel_end'])
                for item in page['events']:
                    if self.boundary and item['cursor'] > self.boundary[0]:
                        break
                    store.append(invocation, {'method':'native/receipt',
                        'received_at':item['received_at'], 'event':item['event']},
                        source='native', cursor=item['cursor'])
                    observed = True
                    terminal_native = terminal_native or item['event'].get('method') == 'turn/completed'
                self.after = page['next_after']
                telemetry=page.get('telemetry',{})
                for item in telemetry.get('events',[]):
                    if self.boundary and item['cursor'] > self.boundary[1]:
                        break
                    store.append(invocation,{'method':'otel/receipt','received_at':item['received_at'],
                        'event':item['event']},source='otel',cursor=item['cursor'])
                self.otel_after=telemetry.get('next_after',self.otel_after)
                drained = self.boundary and self.after >= self.boundary[0] and self.otel_after >= self.boundary[1]
                # Drain the final page before closing; resume must not inherit
                # the previous turn's terminal status before dispatch finishes.
                if (drained or (self.boundary is None and not page.get('has_more') and not telemetry.get('has_more'))) and self.done.is_set():
                    status = self.boundary_status if drained else page.get('status')
                    if status in {'completed','failed','cancelled','timeout'}:
                        store.finish(invocation, 'timed_out' if status == 'timeout' else status,
                                     complete=terminal_native, reason=None if terminal_native else 'native_terminal_event_not_observed',
                                     ended_at=self.boundary_time)
                        return
                if len(page['events']) < 200 and len(telemetry.get('events',[])) < 200:
                    time.sleep(.25)
            store.finish(invocation,'timed_out',reason='observation_deadline_remote_outcome_unknown')
        except Exception:
            store.finish(invocation,'failed',reason='activity_capture_interrupted_remote_outcome_unknown')

    def dispatched(self):
        if self.capture and self.started and self.component.operation != 'start':
            # Freeze source cursors synchronously BEFORE allowing a downstream
            # resume node to dispatch against the same runner run/thread.
            try:
                tail=self.feed(self.run_id,tail=True)
                self.boundary_status=tail.get('status')
                self.boundary_time=now()
                self.boundary=(tail['next_after'],tail.get('telemetry',{}).get('next_after',0))
            except Exception:
                self.capture[0].finish(self.capture[1],'failed',reason='invocation_boundary_unverified')
        self.done.set()
        if self.capture and not self.started:
            self.capture[0].finish(self.capture[1],'failed',reason='dispatch_not_bound')


def dispatch_with_capture(component, prepared):
    # Status/cancel inspect existing invocations; they are not new agent work.
    if component.operation not in {'fresh','start','resume'}:
        return component._http(*prepared)
    capture = RunnerCapture(component)
    component._activity_capture = capture
    try:
        if component.operation == 'resume':
            capture.prepare_resume(component._reference_run_id)
        return component._http(*prepared)
    finally:
        capture.dispatched()
