// Scripted no-model agent fixture; not a model exercising judgment.
import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';

const repository = 'example/disposable';
const operations = [];
const git = (...args) => execFileSync('git', ['-c', 'safe.directory=/draft', ...args],
                                     { cwd: '/draft', encoding: 'utf8' }).trim();
function mediate(operation, payload, effect_id) {
  const request = { repository, operation, payload };
  if (effect_id) request.effect_id = effect_id;
  let output;
  try {
    output = execFileSync('node', ['/run/laomedo/mediate.mjs'],
                         { input: JSON.stringify(request), encoding: 'utf8', timeout: 20000 });
  } catch (error) {
    output = error.stdout?.toString() ?? '';
  }
  const response = JSON.parse(output);
  operations.push({ operation, state: response.state ?? 'denied', code: response.error ?? null });
  return response;
}
function confirmed(value) {
  if (value.state !== 'confirmed') throw new Error('unconfirmed_effect_no_retry');
  return value.result;
}

writeFileSync('/draft/change.txt', 'scripted candidate\n');
git('add', 'change.txt');
git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
    'commit', '--quiet', '-m', 'scripted candidate');
const commit = git('rev-parse', 'HEAD');
git('bundle', 'create', '/draft/.laomedo-handoff.bundle', 'refs/heads/run-branch');
confirmed(mediate('bundle_freeze', { attempt_id: 'delivery-attempt' }));
let verified = false;
const deadline = Date.now() + 30000;
while (Date.now() < deadline) {
  const status = mediate('bundle_status', { stage_attempt_id: 'delivery-attempt', commit });
  if (status.state === 'confirmed') { verified = true; break; }
  // Read-only status polling schedules no stage or provider write.
  await new Promise(resolve => setTimeout(resolve, 200));
}
if (!verified) throw new Error('verification_pending_no_retry');
confirmed(mediate('git_push', { branch: 'run-branch', commit,
                             stage_attempt_id: 'delivery-attempt' }, 'delivery-push'));
const marker = 'exp104-delivery-s1-20261009';
const created = confirmed(mediate('pr_create', { title: 'Fixture PR', body: marker + '\nInitial body',
                                               head: 'run-branch', base: 'main', marker }, 'delivery-create'));
const read = confirmed(mediate('pr_read', { number: created.number }));
const stale = mediate('pr_update', { number: created.number, title: 'Fixture PR',
    body: marker + '\nIncorrect stale correction', head: 'run-branch', base: 'main', marker,
    expected: { title: read.title, body: 'not the current body', head_sha: commit } }, 'delivery-stale');
if (stale.state !== 'rejected') throw new Error('stale_update_not_refused');
const unbound = mediate('pr_read', { number: 999 });
if (unbound.state === 'confirmed') throw new Error('unbound_pr_not_refused');
const finalBody = marker + '\nVerified scripted delivery';
confirmed(mediate('pr_update', { number: created.number, title: 'Fixture PR', body: finalBody,
    head: 'run-branch', base: 'main', marker,
    expected: { title: read.title, body: read.body, head_sha: commit } }, 'delivery-correct'));
const final = confirmed(mediate('pr_read', { number: created.number }));
if (final.body !== finalBody || final.head.sha !== commit) throw new Error('final_readback_mismatch');
// Keep this container alive for host post-completion/revocation controls.
writeFileSync('/draft/delivery-result.json', JSON.stringify({ commit, number: created.number,
                                                          final_body: final.body, operations }) + '\n');
await new Promise(resolve => setTimeout(resolve, 90000));
