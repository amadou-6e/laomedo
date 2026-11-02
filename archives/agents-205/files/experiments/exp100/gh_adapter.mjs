// Experimental partial gh syntax adapter; never invokes gh or reads its login.
import { openSync, closeSync, readSync, fstatSync, lstatSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { pathToFileURL } from 'node:url';

export class AdapterError extends Error {
  constructor(code, exit = 2) { super(code); this.exit = exit; }
}
const fail = code => { throw new AdapterError(code); };
function options(args, permitted) {
  const flags = {}, positional = [];
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (!arg.startsWith('-')) { positional.push(arg); continue; }
    if (!permitted.includes(arg) || Object.hasOwn(flags, arg)) fail('unsupported_syntax');
    const value = args[++i];
    if (!value || value.startsWith('--')) fail('unsupported_syntax');
    flags[arg] = value;
  }
  return { flags, positional };
}
function positive(value) {
  if (!/^[1-9][0-9]*$/.test(value ?? '') || !Number.isSafeInteger(Number(value))) fail('unsupported_target');
  return Number(value);
}
function bounded(value) {
  if (typeof value !== 'string' || Buffer.byteLength(value, 'utf8') > 65536 || value.includes('\0')) fail('input_invalid');
  return value;
}
function body(flags, readBody) {
  if (Object.hasOwn(flags, '--body') === Object.hasOwn(flags, '--body-file')) fail('explicit_body_required');
  return bounded(Object.hasOwn(flags, '--body') ? flags['--body'] : readBody(flags['--body-file']));
}
function confirmed(value) {
  if (value?.state === 'confirmed') return value.result;
  if (value?.state === 'rejected' || value?.error) {
    const code = /^[a-z0-9_]{1,128}$/.test(value.error ?? '') ? value.error : 'unspecified';
    throw new AdapterError('mediator_denied:' + code, 3);
  }
  throw new AdapterError('effect_unknown_no_retry', 4);
}

export function plan(argv, context, readBody) {
  const repository = context.repository;
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository ?? '')) fail('repository_required');
  let kind, tail, permitted = ['--repo'];
  if (argv[0] === 'api') {
    kind = 'api'; tail = argv.slice(1); permitted.push('--method');
  } else {
    kind = argv.slice(0, 2).join(' '); tail = argv.slice(2);
    if (kind === 'pr create') permitted.push('--title', '--body', '--body-file', '--head', '--base');
    else if (kind === 'pr edit') permitted.push('--title', '--body', '--body-file');
    else if (!['pr view', 'run list'].includes(kind)) fail('unsupported_command');
  }
  const { flags, positional } = options(tail, permitted);
  if (flags['--repo'] && flags['--repo'] !== repository) fail('repository_mismatch');
  const request = (operation, payload) => ({ repository, operation, payload });
  if (kind === 'pr view') {
    if (positional.length !== 1) fail('unsupported_syntax');
    return { request: request('pr_read', { number: positive(positional[0]) }) };
  }
  if (kind === 'run list') {
    if (positional.length) fail('unsupported_syntax');
    return { request: request('actions_read', { resource: 'runs' }) };
  }
  if (kind === 'api') {
    if (positional.length !== 1 || (flags['--method'] ?? 'GET') !== 'GET') fail('unsupported_api');
    const path = positional[0].startsWith('/') ? positional[0] : '/' + positional[0];
    if (!path.startsWith('/repos/' + repository + '/') || /\.\.|\/\/|[\\%?#]/.test(path)) fail('unsupported_api');
    return { request: request('api_rest_read', { method: 'GET', path }) };
  }
  if (!/^[A-Za-z0-9_.-]{1,128}$/.test(context.effect ?? '') || !context.marker) fail('durable_effect_required');
  if (!flags['--title']) fail('explicit_title_required');
  if (kind === 'pr create' && (positional.length || !flags['--head'] || !flags['--base'])) fail('explicit_target_required');
  if (kind === 'pr edit' && positional.length !== 1) fail('unsupported_syntax');
  const content = body(flags, readBody), title = bounded(flags['--title']);
  if (!content.includes(context.marker)) fail('reconciliation_marker_required');
  if (kind === 'pr create') return { request: {
    ...request('pr_create', { title, body: content, head: flags['--head'], base: flags['--base'], marker: context.marker }),
    effect_id: context.effect } };
  return { edit: { number: positive(positional[0]), title, body: content, marker: context.marker },
           repository, effect: context.effect };
}

export async function execute(argv, context, dependencies) {
  const planned = plan(argv, context, dependencies.readBody);
  if (planned.request) return confirmed(await dependencies.mediate(planned.request));
  const existing = confirmed(await dependencies.mediate({ repository: planned.repository,
    operation: 'pr_read', payload: { number: planned.edit.number } }));
  if (existing?.number !== planned.edit.number || existing?.head?.repository !== planned.repository ||
      !/^[0-9a-f]{40}$/.test(existing?.head?.sha ?? '') || !existing?.head?.branch || !existing.base ||
      typeof existing.title !== 'string' || typeof existing.body !== 'string') fail('readback_invalid');
  return confirmed(await dependencies.mediate({ repository: planned.repository, operation: 'pr_update',
    effect_id: planned.effect, payload: { ...planned.edit, head: existing.head.branch, base: existing.base,
      expected: { title: existing.title, body: existing.body, head_sha: existing.head.sha } } }));
}

export function readBody(path) {
  if (path !== '-' && !lstatSync(path).isFile()) fail('body_file_invalid');
  const source = path === '-' ? 0 : openSync(path, 'r');
  try {
    if (path !== '-' && (!fstatSync(source).isFile() || fstatSync(source).size > 65536)) fail('body_file_invalid');
    // Read at most limit+1, including stdin; never allocate for all input.
    const bytes = Buffer.alloc(65537);
    let length = 0, count;
    while (length < bytes.length && (count = readSync(source, bytes, length, bytes.length - length, null)) > 0) length += count;
    if (length > 65536) fail('body_file_invalid');
    return new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes.subarray(0, length));
  } finally { if (path !== '-') closeSync(source); }
}
function mediate(request) {
  try {
    const raw = execFileSync('node', ['/run/laomedo/mediate.mjs'], {
      input: JSON.stringify(request), encoding: 'utf8', timeout: 20000, maxBuffer: 2 * 1024 * 1024 });
    return JSON.parse(raw);
  } catch (failure) {
    try { return JSON.parse(failure.stdout?.toString() ?? ''); }
    catch { throw new AdapterError('effect_unknown_no_retry', 4); }
  }
}
if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  try {
    const result = await execute(process.argv.slice(2), {
      repository: process.env.LAOMEDO_REPOSITORY, effect: process.env.LAOMEDO_EFFECT_ID,
      marker: process.env.LAOMEDO_RECONCILIATION_MARKER }, { readBody, mediate });
    process.stdout.write(JSON.stringify(result) + '\n');
  } catch (failure) {
    process.stderr.write((failure instanceof AdapterError ? failure.message : 'adapter_input_failed') + '\n');
    process.exitCode = failure instanceof AdapterError ? failure.exit : 2;
  }
}
