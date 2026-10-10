import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from experiments.exp66.native_probe import finish


class NativeProbeCleanupTests(unittest.TestCase):
    def test_locked_ledger_cannot_skip_cleanup_or_teardown_record(self):
        operations = []
        server = Mock()
        server.shutdown.side_effect = lambda: operations.append('shutdown')
        server.server_close.side_effect = lambda: operations.append('close')
        thread = Mock()
        thread.is_alive.return_value = False
        thread.join.side_effect = lambda **kwargs: operations.append('join')

        def cleanup(*args):
            operations.append('cleanup')
            return [{'exact_cleanup_verified': True}]

        def locked(*args, **kwargs):
            operations.append('ledger')
            raise FileExistsError('private lock path must not enter evidence')

        with tempfile.TemporaryDirectory() as directory, patch(
                'experiments.exp66.native_probe._cleanup_runner_runs', side_effect=cleanup), patch(
                'experiments.exp66.native_probe.reserve_entry', side_effect=locked):
            state = Path(directory)
            finish(state, 'before', 'entry', 'submitted_unknown', Mock(),
                   'native-id', server, thread, {})
            result = json.loads((state/'teardown.json').read_text())
        self.assertEqual(operations, ['cleanup', 'shutdown', 'close', 'join', 'ledger'])
        self.assertTrue(result['exact_cleanup_verified'])
        self.assertTrue(result['runner_server_stopped'])
        self.assertEqual(result['ledger_update_error_class'], 'FileExistsError')
        self.assertNotIn('private lock path', json.dumps(result))

    def test_cleanup_failure_still_stops_server_and_finalizes_ledger(self):
        server, thread = Mock(), Mock()
        thread.is_alive.return_value = False
        with tempfile.TemporaryDirectory() as directory, patch(
                'experiments.exp66.native_probe._cleanup_runner_runs',
                side_effect=RuntimeError('private detail')), patch(
                'experiments.exp66.native_probe.reserve_entry') as ledger:
            state = Path(directory)
            finish(state, 'during', 'entry', 'submitted_unknown', Mock(),
                   'native-id', server, thread, {})
            result = json.loads((state/'teardown.json').read_text())
            ledger.assert_called_once()
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()
        thread.join.assert_called_once_with(timeout=3)
        self.assertEqual(result['cleanup_error_class'], 'RuntimeError')
        self.assertNotIn('exact_cleanup_verified', result)
        self.assertNotIn('private detail', json.dumps(result))
