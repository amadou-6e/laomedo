"""Internal control-protocol regressions; real-account acceptance is separate."""
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from laomedo.agents.providers.claude_runner import ClaudeRunner, command, normalize_models
from laomedo.agents.local_runner import RunnerError


def native(model='fable', levels=None):
    return {'value':model,'resolvedModel':'claude-fable-test','displayName':'Fable test',
            'supportsEffort':True,'supportedEffortLevels':levels or ['low','high','xhigh','max']}


class ClaudeModelTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.runner=object.__new__(ClaudeRunner)
        self.runner.state=Path(self.temp.name)
        self.runner.executable='claude'
        self.runner.container=SimpleNamespace(control=lambda *a,**k:None)
        self.runner._catalog_lock=threading.Lock()
        self.auth=patch.object(self.runner,'_check_auth');self.auth.start();self.addCleanup(self.auth.stop)

    def transport(self, *, mutate=None, items=None):
        def run(args, **kwargs):
            self.assertNotIn('--model',args)
            self.assertIn('--no-session-persistence',args)
            self.assertIn('--restricted',args)
            self.assertEqual(kwargs['timeout'],45)
            sent=[json.loads(line) for line in kwargs['input'].splitlines()]
            self.assertEqual(len(sent),1)
            self.assertEqual(sent[0]['type'],'control_request')
            self.assertEqual(sent[0]['request'],{'subtype':'initialize','hooks':{}})
            value={'type':'control_response','response':{'subtype':'success',
                'request_id':sent[0]['request_id'],'response':{'models':items or [native()]}}}
            if mutate: mutate(value)
            return subprocess.CompletedProcess(args,0,stdout=(json.dumps(value)+'\n').encode())
        return patch.object(self.runner.container,'control',side_effect=run)

    def test_native_catalog_has_account_labels_exact_ids_efforts_and_no_user_message(self):
        with self.transport(): result=self.runner.model_catalog()
        self.assertEqual(result['models'],[{'id':'fable','name':'Fable test',
            'resolved_model':'claude-fable-test','efforts':['low','high','xhigh','max']}])
        self.assertEqual(result['source'],'claude_cli_initialize')
        self.assertEqual(result['account_availability'],'cli_reported')
        self.assertEqual(result['submitted_turns'],0)
        self.runner._check_auth.assert_called_once_with(timeout=15)
        self.assertEqual(list(self.runner.state.iterdir()),[])

    def test_timeout_and_native_errors_are_safe_and_release_lock(self):
        for error in (subprocess.TimeoutExpired(['private-control'],18,output=b'secret'),OSError('secret')):
            with patch.object(self.runner.container,'control',side_effect=error):
                with self.assertRaisesRegex(RunnerError,'^runner_model_catalog_unavailable_check_runner_connection$'):
                    self.runner.model_catalog()
            self.assertFalse(self.runner._catalog_lock.locked())
        with self.transport(): self.assertEqual(len(self.runner.model_catalog()['models']),1)

    def test_wrong_identity_duplicate_models_and_error_response_fail_closed(self):
        for mutate in (lambda v:v['response'].update(request_id='wrong'),
                       lambda v:v['response'].update(subtype='error',error='secret'),
                       lambda v:v.update(type='assistant')):
            with self.transport(mutate=mutate):
                with self.assertRaisesRegex(RunnerError,'^runner_model_catalog_unavailable_check_runner_connection$'):
                    self.runner.model_catalog()
        with self.assertRaises(ValueError): normalize_models([native(),native()])

    def test_refresh_does_not_serve_stale_catalog_or_hardcoded_fallback(self):
        with self.transport(): self.assertEqual(self.runner.model_catalog()['models'][0]['id'],'fable')
        with self.transport(items=[native('new-model')]):
            self.assertEqual(self.runner.model_catalog(refresh=True)['models'][0]['id'],'new-model')
        with patch.object(self.runner.container,'control',side_effect=OSError('offline')):
            with self.assertRaises(RunnerError): self.runner.model_catalog(refresh=True)

    def test_no_effort_model_omits_flag_and_invalid_metadata_is_rejected(self):
        model={'value':'claude-haiku-old','resolvedModel':'claude-haiku-old','displayName':'Haiku old'}
        self.assertEqual(normalize_models([model])[0]['efforts'],['default'])
        args=command('cli','claude-haiku-old','default','00000000-0000-4000-8000-000000000001')
        self.assertNotIn('--effort',args)
        for levels in (['unsupported'],['low','low'],[{}]):
            with self.assertRaises(ValueError): normalize_models([native(levels=levels)])

    def test_concurrent_refreshes_share_one_native_discovery_and_do_not_cache_next_refresh(self):
        from concurrent.futures import ThreadPoolExecutor
        entered=threading.Event();release=threading.Event()
        def discover():
            entered.set();self.assertTrue(release.wait(timeout=5))
            return {'models':[{'id':'native'}]}
        with patch.object(self.runner,'_discover_models',side_effect=discover) as run:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first=pool.submit(self.runner.model_catalog);self.assertTrue(entered.wait(timeout=5))
                waiting=threading.Event();original=self.runner._catalog_pending.result
                def wait_result(*args,**kwargs):
                    waiting.set();return original(*args,**kwargs)
                with patch.object(self.runner._catalog_pending,'result',side_effect=wait_result):
                    second=pool.submit(self.runner.model_catalog)
                    self.assertTrue(waiting.wait(timeout=5));release.set()
                    self.assertEqual(first.result(timeout=5),second.result(timeout=5))
            self.assertEqual(run.call_count,1)
            self.runner.model_catalog();self.assertEqual(run.call_count,1)
            self.runner.model_catalog(refresh=True);self.assertEqual(run.call_count,2)
