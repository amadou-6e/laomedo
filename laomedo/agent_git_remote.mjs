// Native Git remote-helper protocol; the host alone owns provider credentials.
import { execFileSync } from 'node:child_process';
import { createInterface } from 'node:readline';
import { readFileSync, writeFileSync, mkdirSync, openSync, closeSync, unlinkSync, fsyncSync, renameSync } from 'node:fs';
import { resolve, join } from 'node:path';
import { createHash } from 'node:crypto';
import { pathToFileURL } from 'node:url';

export class RemoteError extends Error {}
const fail = code => { throw new RemoteError(code); };
const sha = value => /^[0-9a-f]{40}$/.test(value ?? '');
const git = (...args) => execFileSync('git', args, { encoding: 'utf8', timeout: 30000,
  maxBuffer: 1024 * 1024, stdio: ['ignore', 'pipe', 'pipe'] }).trim();
export function target(url, context) {
  // Git strips the explicit helper prefix before argv[2]; accept only that
  // exact repository (or the full URL in direct protocol controls).
  if (![context.repository, 'laomedo::' + context.repository].includes(url) ||
      !/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(context.repository ?? '') ||
      !/^[A-Za-z0-9][A-Za-z0-9_./-]{0,127}$/.test(context.branch ?? '') ||
      context.branch.includes('..')) fail('remote_scope_invalid');
}
function confirmed(value) {
  if (value?.state === 'confirmed') return value.result;
  if (value?.state === 'rejected' || value?.error) fail('mediation_denied');
  fail('effect_unknown_no_retry');
}
function mediate(repository, operation, payload, effect_id) {
  let raw;
  try { raw = execFileSync('node', ['/run/laomedo/mediate.mjs'], {
    input: JSON.stringify({ repository, operation, payload, ...(effect_id ? { effect_id } : {}) }),
    encoding: 'utf8', timeout: 20000, maxBuffer: 1024 * 1024 }); }
  catch (error) { raw = error.stdout?.toString(); }
  try { return confirmed(JSON.parse(raw)); }
  catch (error) { if (error instanceof RemoteError) throw error; fail('effect_unknown_no_retry'); }
}
export function pushTarget(commands, branch) {
  if (commands.length !== 1) fail('multiple_refs_unsupported');
  const parts = commands[0].slice(5).split(':');
  if (parts.length !== 2 || !['HEAD', 'refs/heads/' + branch].includes(parts[0]) ||
      parts[1] !== 'refs/heads/' + branch) fail('push_target_denied');
  return parts;
}
async function push(commands, context) {
  const [source, destination] = pushTarget(commands, context.branch);
  const commit = git('rev-parse', '--verify', source + '^{commit}');
  if (!sha(commit) || git('rev-parse', '--verify', 'refs/heads/' + context.branch) !== commit)
    fail('push_branch_commit_mismatch');
  const metadata = resolve(git('rev-parse', '--git-dir'), 'laomedo-helper');
  mkdirSync(metadata, { recursive: true });
  const lock = join(metadata, 'handoff.lock');
  let descriptor;
  try { descriptor = openSync(lock, 'wx'); } catch { fail('handoff_busy'); }
  try {
    const digest = createHash('sha256').update(context.repository + '\n' + context.branch + '\n' + commit).digest('hex');
    const identity = 'native-' + digest;
    const journal = join(metadata, digest + '.json');
    let record;
    try { record = JSON.parse(readFileSync(journal, 'utf8')); }
    catch (error) {
      if (error.code !== 'ENOENT') fail('journal_invalid');
      record = { commit, branch: context.branch, identity, phase: 'reserved' };
      const fd = openSync(journal, 'wx');
      try { writeFileSync(fd, JSON.stringify(record)); fsyncSync(fd); } finally { closeSync(fd); }
    }
    if (record.commit !== commit || record.branch !== context.branch || record.identity !== identity)
      fail('journal_invalid');
    const save = phase => {
      record.phase = phase;
      const temporary = journal + '.next';
      const fd = openSync(temporary, 'wx');
      try { writeFileSync(fd, JSON.stringify(record)); fsyncSync(fd); } finally { closeSync(fd); }
      renameSync(temporary, journal);
    };
    const payload = { branch: context.branch, commit, stage_attempt_id: identity };
    if (record.phase === 'push_requested' || record.phase === 'confirmed') {
      // The broker owns exactly-once/unknown handling; reuse the same request.
      const result = mediate(context.repository, 'git_push', payload, identity);
      if (result?.commit !== commit || result?.branch !== context.branch) fail('push_readback_invalid');
      save('confirmed');
    } else {
      if (record.phase !== 'reserved') fail('freeze_unknown_no_retry');
      git('bundle', 'create', resolve('.laomedo-handoff.bundle'), 'refs/heads/' + context.branch);
      // Save before asking to freeze; interrupted capture is never reissued.
      save('freeze_requested');
      mediate(context.repository, 'bundle_freeze', { attempt_id: identity });
      save('frozen');
      const deadline = Date.now() + 60000;
      let verified = false;
      do {
        try {
          const result = mediate(context.repository, 'bundle_status', { stage_attempt_id: identity, commit });
          verified = result?.commit === commit && result?.stage_attempt_id === identity;
        } catch (error) { if (error.message !== 'effect_unknown_no_retry') throw error; }
        if (!verified) await new Promise(resolve => setTimeout(resolve, 250));
      } while (!verified && Date.now() < deadline);
      if (!verified) fail('stage_pending_no_retry');
      save('push_requested');
      const result = mediate(context.repository, 'git_push', payload, identity);
      if (result?.commit !== commit || result?.branch !== context.branch) fail('push_readback_invalid');
      save('confirmed');
    }
    return 'ok ' + destination + '\n\n';
  } finally { closeSync(descriptor); unlinkSync(lock); }
}
async function main() {
  const context = { repository: process.env.LAOMEDO_REPOSITORY, branch: process.env.LAOMEDO_RUN_BRANCH };
  target(process.argv[3], context);
  let batch = [], advertised = new Map();
  const lines = createInterface({ input: process.stdin, crlfDelay: Infinity });
  for await (const line of lines) {
    if (line === 'capabilities') process.stdout.write('push\nfetch\noption\n\n');
    else if (line.startsWith('option ')) process.stdout.write(
      /^option (verbosity|progress) /.test(line) ? 'ok\n' : 'unsupported\n');
    else if (line === 'list for-push') process.stdout.write('\n');
    else if (line === 'list') {
      const result = mediate(context.repository, 'git_fetch', { action: 'list' });
      if (!Array.isArray(result?.refs) || result.refs.length > 2) fail('fetch_readback_invalid');
      advertised = new Map();
      for (const item of result.refs) {
        if (!sha(item.commit) || !['refs/heads/main', 'refs/heads/' + context.branch].includes(item.ref) ||
            advertised.has(item.ref)) fail('fetch_readback_invalid');
        advertised.set(item.ref, item.commit);
      }
      for (const [ref, commit] of advertised) process.stdout.write(commit + ' ' + ref + '\n');
      process.stdout.write('\n');
    } else if (line.startsWith('push ') || line.startsWith('fetch ')) batch.push(line);
    else if (line === '' && batch.length) {
      if (batch.every(item => item.startsWith('push '))) process.stdout.write(await push(batch, context));
      else if (batch.every(item => item.startsWith('fetch '))) {
        // Validate the entire batch before any remote acquisition.
        const items = batch.map(item => item.split(' '));
        if (items.some(item => item.length !== 3 || advertised.get(item[2]) !== item[1])) fail('fetch_target_denied');
        for (const [, commit, ref] of items) {
          const result = mediate(context.repository, 'git_fetch', { action: 'fetch', ref, commit });
          if (result?.commit !== commit || result.ref !== ref || typeof result.bundle !== 'string' ||
              result.bundle.length > 350000) fail('fetch_readback_invalid');
          const bytes = Buffer.from(result.bundle, 'base64');
          if (bytes.length > 262144 || bytes.toString('base64') !== result.bundle) fail('fetch_readback_invalid');
          const dir = resolve(git('rev-parse', '--git-dir'), 'laomedo-helper');
          mkdirSync(dir, { recursive: true });
          const path = join(dir, 'fetch-' + commit + '.bundle');
          let created = false;
          try {
            writeFileSync(path, bytes, { flag: 'wx' });
            created = true;
            if (git('bundle', 'list-heads', path) !== commit + ' refs/heads/laomedo-read') fail('fetch_readback_invalid');
            git('-c', 'core.hooksPath=/dev/null', 'fetch', '--no-tags', '--no-write-fetch-head', path, 'refs/heads/laomedo-read');
          } finally { if (created) { try { unlinkSync(path); } catch {} } }
        }
        process.stdout.write('\n');
      } else fail('mixed_batch_unsupported');
      batch = [];
    } else if (line !== '') fail('unsupported_protocol');
  }
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  main().catch(error => {
    // Git waits for protocol output before closing stdin. On refusal the
    // readline handle must not keep the helper alive and deadlock Git.
    process.stderr.write((error instanceof RemoteError ? error.message : 'remote_helper_failed') + '\n',
      () => process.exit(1));
  });
}
