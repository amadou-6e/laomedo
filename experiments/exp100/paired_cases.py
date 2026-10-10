"""Frozen input vectors. The controller constructs review bytes, not the agent."""
from laomedo.github_rest_transport import ISSUE_GRAPHQL_QUERY

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


def check(observation):
    if observation.get('identity') != IDENTITY or not observation.get('cleanup_verified'):
        raise ValueError('identity_or_cleanup_invalid')
    rows = observation['cases']
    if len(rows) != len(REQUIRED) or {row['case'] for row in rows} != REQUIRED:
        raise ValueError('missing_or_repeated_case')
    for row in rows:
        if row.get('run_id') != IDENTITY + '-' + row['run']:
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
        elif classification == 'unknown':
            if row['mediated']['exit'] != 4:
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
