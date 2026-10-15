"""Observe only a runner-accepted attempt, never a neighbouring invocation."""
import json
import os
from pathlib import Path
import threading
import time
from uuid import UUID
from urllib.request import Request, build_opener, ProxyHandler

from .agent_activity import capture_for

REFUSALS = {'runner_busy','run_not_dispatchable','resume_binding_mismatch',
            'post_run_snapshot_mismatch','workspace_changed_since_snapshot',
            'protected_mount_changed','activity_attempt_already_exists',
            'publication_handoff_resume_denied','resume_after_runner_restart_forbidden',
            'resume_auth_identity_mismatch'}


class RunnerCapture:
    def __init__(self, component):
        self.capture = capture_for(component)
        self.done = threading.Event()
        self.refused = threading.Event()
        self.started = False
        self.accepted = False
        self.attempt_id = None
        self.outcome = None
        self.component = component
        self.base = str(component.runner_url).rstrip('/')
        self.timeout = max(30, int(component.timeout_seconds) + 30)
        self.opener = build_opener(ProxyHandler({}))
        if self.capture:
            try:
                path=os.environ.get('LAOMEDO_RUNNER_TOKEN_FILE','/run/secrets/laomedo-runner-token')
                self.token=Path(path).read_text().strip()
                if not self.token:
                    raise ValueError('activity_runner_token_missing')
            except Exception:
                self.capture[0].finish(self.capture[1],'failed',reason='activity_runner_auth_unavailable')
                raise

    def feed(self, run_id, after, otel_after):
        url=f'{self.base}/v1/runs/{run_id}/events?attempt={self.attempt_id}&after={after}&otel_after={otel_after}&limit=200'
        with self.opener.open(Request(url,headers={'Authorization':'Bearer '+self.token}),timeout=10) as response:
            value=json.load(response)
        if value.get('run_id') != run_id:
            raise ValueError('activity_runner_identity_mismatch')
        if value.get('accepted') and value.get('attempt',{}).get('id') != self.attempt_id:
            raise ValueError('activity_attempt_identity_mismatch')
        return value

    def bind(self, run_id, attempt_id=None):
        if not self.capture or self.started:
            return
        if not isinstance(attempt_id,str) or str(UUID(attempt_id)) != attempt_id:
            raise ValueError('activity_attempt_identity_required')
        self.attempt_id=attempt_id
        self.capture[0].bind(self.capture[1],run_id)
        self.started=True
        threading.Thread(target=self.observe,args=(run_id,),daemon=True,
                         name='laomedo-activity-observer').start()

    def observe(self, run_id):
        store,invocation=self.capture
        after=otel_after=0
        deadline=time.monotonic()+self.timeout
        failures=0
        terminal_native=False
        try:
            while time.monotonic()<deadline:
                if self.refused.is_set():
                    return
                try:
                    page=self.feed(run_id,after,otel_after)
                    failures=0
                except Exception:
                    failures+=1
                    if failures>=3:
                        raise
                    time.sleep(.3)
                    continue
                if not page.get('accepted'):
                    if self.done.is_set() and self.outcome in {'completed','failed','cancelled','timeout'}:
                        store.finish(invocation,'failed',reason='dispatch_not_accepted')
                        return
                    time.sleep(.25)
                    continue
                attempt=page['attempt']
                if not self.accepted:
                    if not store.claim_attempt(invocation,run_id,self.attempt_id):
                        store.finish(invocation,'completed',reason='existing_attempt_reference_no_new_usage')
                        return
                    self.accepted=True
                    after=attempt['native_start']
                    otel_after=attempt['otel_start']
                    store.append(invocation,{'method':'capture/usageBaseline','threads':attempt['usage_baseline']})
                store.bind(invocation,run_id,native_session=page.get('thread_id'),model=page.get('model'))
                for item in page['events']:
                    store.append(invocation,{'method':'native/receipt','received_at':item['received_at'],'event':item['event']},
                                 source='native',cursor=item['cursor'])
                    terminal_native=terminal_native or item['event'].get('method')=='turn/completed'
                after=page['next_after']
                telemetry=page.get('telemetry',{})
                for item in telemetry.get('events',[]):
                    store.append(invocation,{'method':'otel/receipt','received_at':item['received_at'],'event':item['event']},
                                 source='otel',cursor=item['cursor'])
                otel_after=telemetry.get('next_after',otel_after)
                if (attempt.get('native_end') is not None and after>=attempt['native_end']
                        and otel_after>=attempt['otel_end']):
                    status=attempt['status']
                    if status in {'completed','failed','cancelled','timeout'}:
                        store.finish(invocation,'timed_out' if status=='timeout' else status,
                            complete=terminal_native,reason=None if terminal_native else 'native_terminal_event_not_observed',
                            ended_at=attempt['ended_at'])
                        return
                if not page.get('has_more') and not telemetry.get('has_more'):
                    time.sleep(.25)
            store.finish(invocation,'timed_out',reason='observation_deadline_remote_outcome_unknown')
        except Exception:
            store.finish(invocation,'failed',reason='activity_capture_interrupted_remote_outcome_unknown')

    def dispatched(self, *, result=None, refused=False):
        self.outcome=(result or {}).get('status')
        if refused:
            self.refused.set()
            if self.capture:
                self.capture[0].finish(self.capture[1],'failed',reason='dispatch_refused')
        self.done.set()
        if self.capture and not self.started:
            self.capture[0].finish(self.capture[1],'failed',reason='dispatch_not_bound')


def dispatch_with_capture(component, prepared):
    if component.operation not in {'fresh','start','resume'}:
        return component._http(*prepared)
    capture=RunnerCapture(component)
    component._activity_capture=capture
    result=None
    refused=False
    try:
        if component.operation=='resume' and capture.capture:
            endpoint,payload,method=prepared
            payload={**payload,'activity_attempt_id':capture.capture[1]}
            prepared=(endpoint,payload,method)
            # This polls only acceptance of our unique ID. It cannot consume
            # native receipts until the runner durably accepts this attempt.
            capture.bind(component._reference_run_id,capture.capture[1])
        result=component._http(*prepared)
        return result
    except Exception as exc:
        reference=getattr(exc,'run_reference',None)
        category=reference.get('error_category') if isinstance(reference,dict) else None
        refused=isinstance(category,str) and category in REFUSALS
        raise
    finally:
        capture.dispatched(result=result,refused=refused)
