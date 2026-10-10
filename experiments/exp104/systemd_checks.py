"""Assess actual S14 captures; never infer a safe result from a timeout."""
def assess(value):
    def require(condition, code):
        if not condition:
            raise ValueError(code)
    require(value.get('status') == 'captured', 'capture_incomplete')
    require(value.get('pid1') == 'systemd', 'systemd_pid1_missing')
    units = value['units']
    require(len({item['ControlGroup'] for item in units.values()}) == 3 and
            all(item['ControlGroup'] and int(item['MainPID']) > 1 and
                item['KillMode'] == 'control-group' and item['Restart'] == 'no'
                for item in units.values()), 'unit_isolation_missing')
    for side, runner in value['runners'].items():
        require(int(units[side]['MainPID']) == runner['pid'] and
                type(runner['child']) is int and runner['child'] != runner['pid'] and
                bool(runner['grant_id']), 'runner_binding_missing')
        require(all(units[side]['ControlGroup'] in value['membership'][side][key]
                    for key in ('pid', 'child')), 'child_membership_missing')
    for side in ('a', 'b'):
        require(value[side + '_initial']['body']['state'] == 'confirmed', 'positive_failed')
    require(value['initial_count'] == value['replay_count'] == 2 and
            value['a_replay'] == value['a_initial'], 'confirmed_redispatched')
    require(value['a_parent_child_gone'] is True, 'tree_kill_missing')
    require(0 <= value['revoked']['revoked_at_monotonic'] - value['kill_finished'] <= 60 and
            value['runners']['a']['grant_id'] in value['revoked']['revoked_grants'],
            'revocation_boundary_missing')
    require(value['a_denied'] == {'http': 403, 'body': {'error': 'grant_unavailable'}} and
            value['before_denial_count'] == value['after_denial_count'] == 2,
            'post_loss_denial_missing')
    require(value['b_after_denial']['body']['state'] == 'confirmed' and
            value['b_effect_at'] > value['denied_at'] and value['after_b_count'] == 3,
            'b_continuity_missing')
    require(all(value['surviving_units'][side]['MainPID'] == units[side]['MainPID']
                for side in ('service', 'b')), 'independent_service_died')
    require(value['unknown']['body']['state'] == value['unknown_replay']['body']['state'] == 'unknown' and
            value['unknown_count'] == value['unknown_replay_count'] == value['conflict_count'] == 4 and
            value['conflict']['http'] == 403 and value['conflict']['body']['error'] == 'effect_conflict',
            'unknown_redispatched')
    require(value['restarted_unit']['MainPID'] != units['service']['MainPID'] and
            value['b_restart_denied'] == {'http': 403, 'body': {'error': 'grant_unavailable'}} and
            value['restart_count'] == 4 and value['old_lease_renewed'] is False,
            'restart_not_fail_closed')
    require(value['expired_renewed'] is False and
            value['expired_invocation'] == {'error': 'grant_unavailable'}, 'expired_grant_accepted')
    return {'systemd_synthetic_boundary': 'passed'}
