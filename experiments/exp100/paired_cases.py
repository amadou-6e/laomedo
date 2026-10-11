"""Frozen input vectors. The controller constructs review bytes, not the agent."""
from laomedo.github_rest_transport import ISSUE_GRAPHQL_QUERY
from hashlib import sha256

IDENTITY = 'exp100-paired-s11-20261010-a'
MARKER = IDENTITY + '-reviewed-request'
PROPOSAL = 'paired-reviewed-proposal'
REVIEWED_ISSUE = {'title': 'Paired reviewed issue', 'body': MARKER + '\nReviewed fixture body',
                  'marker': MARKER, 'reviewed_proposal_id': PROPOSAL}
GRAPHQL_INPUT = {'query': ISSUE_GRAPHQL_QUERY,
                 'variables': {'owner': 'example', 'name': 'disposable'}}
REQUIRED = {'git_local', 'git_fetch_base', 'git_fetch_run', 'git_push_first', 'git_push_second',
    'pr_create_file', 'pr_read', 'pr_edit_stdin', 'pr_list', 'pr_api_create',
    'issue_read', 'issue_list', 'issue_create', 'graphql_read', 'actions_list', 'actions_job',
    'rest_get', 'force_refused', 'other_ref_refused', 'multi_ref_refused',
    'wrong_repository', 'wrong_base', 'wrong_pr', 'changed_pr_snapshot',
    'unreviewed_issue', 'edited_issue', 'graphql_mutation', 'graphql_crossrepo',
    'graphql_paging', 'arbitrary_write', 'api_extra_fields', 'api_default_post',
    'credential_export', 'auth_login', 'alias', 'extension', 'paging',
    'confirmed_replay', 'altered_effect', 'lost_response', 'unknown_replay',
    'revoked_a', 'live_b', 'credential_inventory'}
REFUSALS = {
    'force_refused': (1, 'push_target_denied'), 'other_ref_refused': (1, 'push_target_denied'),
    'multi_ref_refused': (1, 'multiple_refs_unsupported'),
    'wrong_repository': (2, 'repository_mismatch'), 'wrong_base': (3, 'mediator_denied:pr_base_denied'),
    'wrong_pr': (3, 'mediator_denied:pr_read_target_denied'),
    'changed_pr_snapshot': (3, 'mediator_denied:pr_snapshot_changed'),
    'unreviewed_issue': (3, 'mediator_denied:issue_review_denied'),
    'edited_issue': (3, 'mediator_denied:issue_review_denied'),
    'graphql_mutation': (2, 'unsupported_graphql'), 'graphql_crossrepo': (2, 'unsupported_graphql'),
    'graphql_paging': (2, 'unsupported_graphql'), 'arbitrary_write': (2, 'unsupported_api'),
    'api_extra_fields': (2, 'json_input_invalid'), 'api_default_post': (2, 'unsupported_api'),
    'credential_export': (2, 'unsupported_command'), 'auth_login': (2, 'unsupported_command'),
    'alias': (2, 'unsupported_command'), 'extension': (2, 'unsupported_command'),
    'paging': (2, 'unsupported_syntax'), 'altered_effect': (3, 'mediator_denied:effect_conflict'),
    'revoked_a': (3, 'mediator_denied:grant_unavailable')}


def check(observation):
    if observation.get('identity') != IDENTITY or not observation.get('cleanup_verified'):
        raise ValueError('identity_or_cleanup_invalid')
    rows = observation['cases']
    if len(rows) != len(REQUIRED) or {row['case'] for row in rows} != REQUIRED:
        raise ValueError('missing_or_repeated_case')
    for row in rows:
        expected_run = 'b' if row['case'] in {'pr_api_create', 'lost_response', 'unknown_replay', 'api_extra_fields', 'live_b'} else 'a'
        if row.get('run_id') != IDENTITY + '-' + expected_run or row['run'] != expected_run:
            raise ValueError('wrong_run')
        classification = row['classification']
        if classification == 'equivalent':
            if row['direct']['exit'] != 0 or row['mediated']['exit'] != 0 or \
                    row['direct']['normalized'] != row['mediated']['normalized']:
                raise ValueError('false_equivalence')
        elif classification in {'denied', 'unsupported'}:
            permitted_reads = row['case'] == 'changed_pr_snapshot'
            if row['mediated']['exit'] == 0 or row['provider_write_delta'] != 0 or \
                    (not permitted_reads and row['provider_delta'] != 0):
                raise ValueError('refusal_not_enforced')
            if (row['mediated']['exit'], row['mediated']['reason']) != REFUSALS[row['case']]:
                raise ValueError('wrong_refusal_reason')
        elif classification == 'unknown':
            if row['case'] == 'unknown_replay':
                if row['mediated'].get('source') != 'host_saved_request' or \
                        row['mediated']['exit'] is not None or row['mediated']['normalized'] != 'unknown':
                    raise ValueError('host_replay_misrepresented')
            elif row['mediated']['exit'] != 4 or row['mediated']['reason'] != 'effect_unknown_no_retry':
                raise ValueError('uncertainty_lost')
        elif classification != 'different-but-authorized':
            raise ValueError('classification_invalid')
    indexed = {row['case']: row for row in rows}
    for key in ('git_local', 'git_fetch_base', 'git_fetch_run', 'git_push_first', 'git_push_second',
                'pr_create_file', 'pr_read', 'pr_edit_stdin', 'pr_list', 'pr_api_create',
                'issue_read', 'issue_list', 'issue_create', 'graphql_read', 'actions_list',
                'actions_job', 'rest_get', 'live_b'):
        if indexed[key]['classification'] != 'equivalent':
            raise ValueError('positive_not_equivalent')
    for key in ('confirmed_replay', 'unknown_replay', 'revoked_a', 'altered_effect'):
        if indexed[key]['provider_delta'] != 0:
            raise ValueError('duplicate_or_revoked_dispatch')
    if indexed['confirmed_replay']['mediated']['exit'] != 0 or \
            indexed['lost_response']['provider_write_delta'] != 1 or \
            indexed['unknown_replay']['classification'] != 'unknown':
        raise ValueError('effect_journal_invalid')
    inventory = indexed['credential_inventory']['mediated']['normalized']
    if inventory['reusable_credential_present'] or inventory['host_config_present'] or \
            inventory['capability_mount_readonly'] is not True:
        raise ValueError('credential_boundary_invalid')
    if observation['direct_write_count'] != 7 or observation['mediated_write_count'] != 7:
        raise ValueError('write_count_invalid')
    receives = observation['direct_git_receives']
    commits = [indexed[case]['direct']['normalized'] for case in ('git_push_first', 'git_push_second')]
    if receives != [['0' * 40, commits[0], 'refs/heads/run-branch'],
                    [commits[0], commits[1], 'refs/heads/run-branch']]:
        raise ValueError('direct_receiver_journal_invalid')
    expected = {'pr-create': ('a', 'confirmed', 'pr_create'), 'pr-edit': ('a', 'confirmed', 'pr_update'),
        'issue-create': ('a', 'confirmed', 'issue_create'), 'changed-snapshot': ('a', 'rejected', 'pr_update'),
        'api-create': ('b', 'confirmed', 'pr_create'), 'lost-response': ('b', 'unknown', 'pr_update')}
    for case in ('git_push_first', 'git_push_second'):
        commit = indexed[case]['mediated']['normalized']
        effect_id = 'native-' + sha256(('example/disposable\nrun-branch\n' + commit).encode()).hexdigest()
        expected[effect_id] = ('a', 'confirmed', 'git_push')
        if indexed[case]['git_write_delta'] != 1 or indexed[case]['direct_git_write_delta'] != 1:
            raise ValueError('git_write_delta_invalid')
    grants = {row['run_id']: row['grant_id'] for row in observation['grants']}
    records = observation['effect_records']
    if len(records) != len(expected) or {row['effect_id'] for row in records} != set(expected):
        raise ValueError('missing_or_duplicate_durable_effect')
    for row in records:
        run, state, operation = expected[row['effect_id']]
        run_id = IDENTITY + '-' + run
        if (row['run_id'], row['grant_id'], row['state'], row['operation']) != \
                (run_id, grants[run_id], state, operation):
            raise ValueError('durable_effect_attribution_invalid')
    for case in ('pr_create_file', 'pr_edit_stdin', 'pr_api_create', 'issue_create', 'lost_response'):
        if indexed[case]['provider_write_delta'] != 1 or indexed[case]['direct_write_delta'] != 1:
            raise ValueError('per_case_write_delta_invalid')
    if observation['unknown_effect'] != {'run_id': IDENTITY + '-b', 'effect_id': 'lost-response', 'state': 'unknown'}:
        raise ValueError('unknown_effect_mismatch')
    if indexed['git_local']['direct']['normalized'] != indexed['git_local']['mediated']['normalized']:
        raise ValueError('local_output_hash_mismatch')
