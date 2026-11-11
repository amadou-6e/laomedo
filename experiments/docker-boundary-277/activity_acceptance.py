"""Real Codex Activity capture acceptance; prints only aggregate checks."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import threading
import time
from uuid import uuid4


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--implementation', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.implementation / 'src'))
    from laomedo.agents.agents.codex.agent import CodexAgent
    from laomedo.agents.activity.capture import ActivityCapture
    from laomedo.agents.activity.models import ActivityInvocation, CaptureIdentity
    from laomedo.agents.activity.store import ActivityStore
    from laomedo.agents.activity.projection import project
    from laomedo.host.runner.http.server import RunnerServer
    from urllib.request import build_opener, ProxyHandler

    spec = importlib.util.spec_from_file_location('docker_acceptance', Path(__file__).with_name('acceptance.py'))
    acceptance = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(acceptance)
    original_start, original_resume = CodexAgent.start, CodexAgent.resume

    def captured(agent, operation, request=None, run_id=None, **kwargs):
        attempt = str(uuid4()) if run_id else None
        results, errors = [], []
        def execute():
            try:
                if run_id:
                    results.append(original_resume(agent, run_id, activity_attempt_id=attempt, **kwargs))
                else:
                    results.append(original_start(agent, request))
            except Exception as error:
                errors.append(type(error).__name__)
        worker = threading.Thread(target=execute)
        server = RunnerServer(agent, port=0)
        http = threading.Thread(target=server.serve_forever, daemon=True)
        http.start()
        worker.start()
        try:
            deadline = time.monotonic() + 180
            while run_id is None and worker.is_alive() and time.monotonic() < deadline:
                candidates = list((agent.state / 'runs').glob('*/record.json'))
                if candidates:
                    record = json.loads(candidates[0].read_text())
                    run_id, attempt = record['run_id'], record['activity_initial_attempt_id']
                    break
                time.sleep(.1)
            if not run_id:
                raise RuntimeError('run_not_admitted')
            store = ActivityStore(agent.state / 'activity-acceptance.db')
            invocation = store.start(CaptureIdentity.from_values('acceptance-owner', 'flow', operation, provider='codex-cli'))
            capture = ActivityCapture.__new__(ActivityCapture)
            capture.capture = ActivityInvocation(store=store, invocation_id=invocation)
            capture.timeout, capture.attempt_id, capture.accepted = 180, attempt, False
            capture.refused, capture.done = threading.Event(), threading.Event()
            capture.outcome = None
            capture.base = 'http://127.0.0.1:' + str(server.server_port)
            capture.token = agent.api_token
            capture.opener = build_opener(ProxyHandler({}))
            def settled():
                worker.join()
                capture.outcome = results[0]['status'] if results else 'failed'
                capture.done.set()
            threading.Thread(target=settled, daemon=True).start()
            capture.observe(run_id)
            worker.join(timeout=180)
            if worker.is_alive() or errors:
                raise RuntimeError('native_execution_not_settled')
            saved = store.read('acceptance-owner', 'flow', operation, invocation)
            view = project(saved['events'], provider='unused-common-path')
            first = agent.read_activity(run_id, attempt, after=0, limit=1)
            replay = agent.read_activity(run_id, attempt, after=0, limit=1)
            page, count = first, 0
            while True:
                count += len(page.records)
                if not page.has_more:
                    break
                page = agent.read_activity(run_id, attempt, after=page.next_after, limit=1)
            checks = {'stage': 'activity_' + operation, 'status': results[0]['status'],
                      'error': results[0].get('error_category'), 'reason': page.reason,
                      'stream_state': saved['run']['stream_state'], 'closed': page.closed,
                      'complete': page.complete, 'record_count': count,
                      'item_count': len(view['items']), 'stable_replay': first.records == replay.records,
                      'projection_revision': page.projection_revision}
            print(json.dumps(checks), flush=True)
            if checks['status'] != 'completed' or checks['stream_state'] != 'complete' or not page.complete or not count or not checks['stable_replay']:
                raise RuntimeError('activity_acceptance_failed')
            return results[0]
        finally:
            if worker.is_alive() and run_id:
                agent.cancel(run_id)
                worker.join(timeout=120)
            server.shutdown()
            http.join(timeout=5)
            server.server_close()

    def start(agent, request):
        return captured(agent, 'fresh', request=request)

    def resume(agent, run_id, prompt, **kwargs):
        return captured(agent, 'resume', run_id=run_id, task=prompt, **kwargs)

    CodexAgent.start, CodexAgent.resume = start, resume
    try:
        sys.argv = [str(Path(__file__).with_name('acceptance.py')), '--implementation', str(args.implementation), '--execute', '--session-login', '--max-prompts', '2']
        acceptance.main()
    finally:
        CodexAgent.start, CodexAgent.resume = original_start, original_resume


if __name__ == '__main__':
    main()
