// Scripted native command fixture, not a model or a real GitHub provider.
import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';

const outcomes = [];
const invoke = (command, args, extra = {}, expected = 0) => {
  let result;
  try {
    result = { status: 0, stdout: execFileSync(command, args, {
      cwd: '/draft', env: { ...process.env, ...extra }, encoding: 'utf8',
      timeout: 90000, maxBuffer: 1024 * 1024 }).trim() };
  } catch (error) {
    result = { status: error.status, stdout: error.stdout?.toString().trim() ?? '' };
  }
  outcomes.push({ command, args, status: result.status });
  writeFileSync('/draft/.git/native-progress.json', JSON.stringify(outcomes) + '\n');
  if (expected === 'nonzero' ? !Number.isInteger(result.status) || result.status === 0
                            : result.status !== expected) throw new Error('unexpected_command_outcome_no_retry');
  return result.stdout;
};
const git = (...args) => invoke('git', ['-c', 'safe.directory=/draft', ...args]);
const commit = text => {
  writeFileSync('/draft/change.txt', text + '\n');
  git('add', 'change.txt');
  git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
      'commit', '--quiet', '-m', text);
  return git('rev-parse', 'HEAD');
};
git('fetch', 'origin');
const fetchedBase = git('rev-parse', 'refs/remotes/origin/develop');
const first = commit('first scripted native change');
git('push', 'origin', 'HEAD:refs/heads/run-branch');
git('push', 'origin', 'HEAD:refs/heads/run-branch');
const second = commit('second scripted native change');
git('push', 'origin', 'HEAD:refs/heads/run-branch');
const marker = 'exp100-native-s10-20261010-a';
const context = { LAOMEDO_RECONCILIATION_MARKER: marker };
const created = JSON.parse(invoke('gh', ['pr', 'create', '--title', 'Native fixture PR',
  '--body', marker + '\nInitial body', '--head', 'run-branch', '--base', 'develop'],
  { ...context, LAOMEDO_EFFECT_ID: 'native-create' }));
const initial = JSON.parse(invoke('gh', ['pr', 'view', String(created.number)]));
if (initial.head.sha !== second || initial.base !== 'develop') throw new Error('pr_initial_readback');
const finalBody = marker + '\nChecked native PR body';
invoke('gh', ['pr', 'edit', String(created.number), '--title', 'Native fixture PR',
  '--body', finalBody], { ...context, LAOMEDO_EFFECT_ID: 'native-edit' });
const final = JSON.parse(invoke('gh', ['pr', 'view', String(created.number)]));
if (final.body !== finalBody || final.head.sha !== second) throw new Error('pr_final_readback');
invoke('git', ['-c', 'safe.directory=/draft', 'push', '--force', 'origin', 'HEAD:refs/heads/run-branch'], {}, 'nonzero');
invoke('git', ['-c', 'safe.directory=/draft', 'push', 'origin', 'HEAD:refs/heads/other'], {}, 'nonzero');
invoke('git', ['-c', 'safe.directory=/draft', 'push', 'origin', 'HEAD:refs/heads/run-branch', 'HEAD:refs/heads/other'], {}, 'nonzero');
invoke('gh', ['auth', 'token'], {}, 2);
invoke('gh', ['pr', 'view', '999'], {}, 3);
const status = git('status', '--porcelain');
if (status !== '') throw new Error('generated_handoff_staged_in_checkout');
writeFileSync('/draft/.git/native-result.json', JSON.stringify({ first, second, fetchedBase,
  number: created.number, finalBody, outcomes, checkoutClean: true }) + '\n');
// Host independently confirms this invocation is still alive before its controls.
await new Promise(resolve => setTimeout(resolve, 180000));
