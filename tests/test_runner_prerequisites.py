"""Internal prerequisite controls; not live Docker installation acceptance."""
from pathlib import Path
import json
import subprocess
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
from laomedo.host.runner_prerequisites import check_docker, ERROR_CODES


class DockerPrerequisiteTests(TestCase):
    def test_missing_cli_offers_installation_without_claiming_uninstall(self):
        with patch('laomedo.host.runner_prerequisites.shutil.which', return_value=None), \
             patch('laomedo.host.runner_prerequisites.subprocess.run') as run:
            self.assertEqual(check_docker({'PATH':'host-path'}), 'runner_docker_not_installed')
            run.assert_not_called()

    def test_healthy_engine_uses_only_fixed_read_command(self):
        env = {'PATH':'host-path','DOCKER_CONTEXT':'host-context'}
        with patch('laomedo.host.runner_prerequisites.shutil.which', return_value='docker-host'), \
             patch('laomedo.host.runner_prerequisites.subprocess.run', return_value=SimpleNamespace(
                 returncode=0, stdout='29.8.2\n', stderr='')) as run:
            self.assertIsNone(check_docker(env))
        self.assertEqual(run.call_args.args[0], ['docker-host','info','--format','{{.ServerVersion}}'])
        self.assertEqual(run.call_args.kwargs['env'], env)
        self.assertEqual(run.call_args.kwargs['timeout'], 5)

    def test_known_unreachable_engine_is_distinct_from_access_and_unknown_failures(self):
        for error, expected in [('connection refused', 'runner_docker_unavailable'),
                ('open //./pipe/docker_engine: cannot find the file specified', 'runner_docker_unavailable'),
                ('open //./pipe/dockerDesktopLinuxEngine: Das System kann die angegebene Datei nicht finden.', 'runner_docker_unavailable'),
                ('open client-cert.pem: cannot find the file specified', 'runner_docker_check_unconfirmed'),
                ('permission denied: SECRET', 'runner_docker_check_unconfirmed'),
                ('unknown SECRET private detail', 'runner_docker_check_unconfirmed')]:
            with patch('laomedo.host.runner_prerequisites.shutil.which', return_value='docker-host'), \
                 patch('laomedo.host.runner_prerequisites.subprocess.run', return_value=SimpleNamespace(
                     returncode=1, stdout='', stderr=error)):
                self.assertEqual(check_docker({}), expected)

    def test_timeout_os_error_and_malformed_success_are_unconfirmed(self):
        with patch('laomedo.host.runner_prerequisites.shutil.which', return_value='docker-host'):
            for error in (subprocess.TimeoutExpired('private',5), PermissionError('private')):
                with patch('laomedo.host.runner_prerequisites.subprocess.run', side_effect=error):
                    self.assertEqual(check_docker({}), 'runner_docker_check_unconfirmed')
            with patch('laomedo.host.runner_prerequisites.subprocess.run', return_value=SimpleNamespace(
                    returncode=0, stdout='not an engine version', stderr='')):
                self.assertEqual(check_docker({}), 'runner_docker_check_unconfirmed')

    def test_prerequisite_producer_has_complete_catalogue_coverage(self):
        import ast
        from laomedo.host import runner_prerequisites
        source = ast.parse(Path(runner_prerequisites.__file__).read_text())
        emitted = {n.value for n in ast.walk(source) if isinstance(n, ast.Constant)
                   and isinstance(n.value, str) and n.value.startswith('runner_docker_')}
        self.assertEqual(emitted, ERROR_CODES)
        catalogue = json.loads((Path(__file__).resolve().parents[1] /
            'frontend/langflow-skill-viewer/node-error-catalog.json').read_text(encoding='utf-8'))
        self.assertEqual(ERROR_CODES - catalogue.keys(), set())
        for code in ERROR_CODES:
            self.assertTrue(catalogue[code]['description'])
            self.assertTrue(catalogue[code]['recovery'])
