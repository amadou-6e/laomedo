"""No-Docker gates/negative controls for the prospective S14 capture."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from experiments.exp104.systemd_checks import assess
from experiments.exp104 import systemd_probe


def positive():
    confirmed = {'http': 200, 'body': {'state': 'confirmed'}}
    units = {key: {'MainPID': str(pid), 'ControlGroup': '/system.slice/' + key,
                   'KillMode': 'control-group', 'Restart': 'no'}
             for key, pid in [('service', 10), ('a', 11), ('b', 12)]}
    return {'status': 'captured', 'pid1': 'systemd', 'units': units,
        'runners': {'a': {'pid': 11, 'child': 21, 'grant_id': 'grant-a'},
                    'b': {'pid': 12, 'child': 22, 'grant_id': 'grant-b'}},
        'membership': {key: {field: units[key]['ControlGroup'] for field in ('pid', 'child')}
                       for key in ('a', 'b')},
        'a_initial': confirmed, 'b_initial': confirmed, 'a_replay': confirmed,
        'initial_count': 2, 'replay_count': 2, 'a_parent_child_gone': True,
        'kill_finished': 10, 'revoked': {'revoked_at_monotonic': 15, 'revoked_grants': ['grant-a']},
        'a_denied': {'http': 403, 'body': {'error': 'grant_unavailable'}},
        'before_denial_count': 2, 'after_denial_count': 2, 'b_after_denial': confirmed,
        'denied_at': 16, 'b_effect_at': 17, 'after_b_count': 3,
        'surviving_units': {'service': units['service'], 'b': units['b']},
        'unknown': {'http': 200, 'body': {'state': 'unknown'}},
        'unknown_replay': {'http': 200, 'body': {'state': 'unknown'}},
        'unknown_count': 4, 'unknown_replay_count': 4, 'conflict_count': 4,
        'conflict': {'http': 403, 'body': {'error': 'effect_conflict'}},
        'restarted_unit': {'MainPID': '30'},
        'b_restart_denied': {'http': 403, 'body': {'error': 'grant_unavailable'}},
        'restart_count': 4, 'old_lease_renewed': False, 'expired_renewed': False,
        'expired_invocation': {'error': 'grant_unavailable'}}


class SystemdProbeTests(unittest.TestCase):
    def test_complete_fixture_and_each_missing_boundary(self):
        self.assertEqual(assess(positive()), {'systemd_synthetic_boundary': 'passed'})
        for field, replacement in [('pid1', 'init'), ('a_parent_child_gone', False),
                ('a_denied', {'http': 200, 'body': {'state': 'confirmed'}}),
                ('after_denial_count', 3), ('after_b_count', 2),
                ('unknown_replay_count', 5), ('expired_renewed', True),
                ('old_lease_renewed', True)]:
            candidate = deepcopy(positive())
            candidate[field] = replacement
            with self.subTest(field=field), self.assertRaises((ValueError, KeyError)):
                assess(candidate)
        for mutate in [lambda v: v['units']['a'].update(ControlGroup=v['units']['b']['ControlGroup']),
                       lambda v: v['runners']['a'].update(grant_id='wrong-grant'),
                       lambda v: v['membership']['a'].update(child='/outside'),
                       lambda v: v['surviving_units']['b'].update(MainPID='99'),
                       lambda v: v['restarted_unit'].update(MainPID='10')]:
            candidate = deepcopy(positive())
            mutate(candidate)
            with self.assertRaises(ValueError):
                assess(candidate)

    def test_wrong_identity_root_never_invokes_docker(self):
        with patch.object(systemd_probe, 'command') as command:
            with self.assertRaisesRegex(ValueError, 'identity_root_mismatch'):
                systemd_probe.run(Path('/unrelated'), 'source', Path('review'))
            command.assert_not_called()

    def test_daemon_failure_is_not_absence(self):
        failure = type('R', (), {'returncode': 1, 'stderr': b'daemon unavailable'})()
        with patch.object(systemd_probe, 'command', return_value=failure):
            with self.assertRaisesRegex(RuntimeError, 'inspection_unavailable'):
                systemd_probe.inspect('owned-name')

    def test_wrong_review_never_claims_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            review = root / 'review.json'
            review.write_text(json.dumps({'verdict': 'approve'}), encoding='utf-8')
            outputs = [type('R', (), {'stdout': b'exact\n'})(), type('R', (), {'stdout': b''})()]
            with patch.object(systemd_probe.tempfile, 'gettempdir', return_value=folder), \
                    patch.object(systemd_probe, 'command', side_effect=outputs):
                with self.assertRaisesRegex(ValueError, 'review_record_mismatch'):
                    systemd_probe.run(root / systemd_probe.IDENTITY, 'exact', review)
            self.assertFalse((root / (systemd_probe.IDENTITY + '.claimed')).exists())


if __name__ == '__main__':
    unittest.main()
