import assert from 'node:assert/strict';
import test from 'node:test';
import { execute, plan, AdapterError } from './gh_adapter.mjs';

const context = { repository: 'example/disposable', effect: 'effect-1', marker: 'marker' };
const body = 'marker\r\nUnicode: λ\n';
test('supported reads map exact requests', () => {
  assert.deepEqual(plan(['pr', 'view', '7'], context).request,
    { repository: context.repository, operation: 'pr_read', payload: { number: 7 } });
  assert.deepEqual(plan(['run', 'list'], context).request.payload, { resource: 'runs' });
  assert.deepEqual(plan(['api', 'repos/example/disposable/issues', '--method', 'GET'], context).request.payload,
    { method: 'GET', path: '/repos/example/disposable/issues' });
});
test('body file bytes and durable create identity preserved', () => {
  const result = plan(['pr', 'create', '--title', 'Title', '--body-file', '-', '--head', 'branch', '--base', 'main'],
    context, path => { assert.equal(path, '-'); return body; });
  assert.equal(result.request.payload.body, body);
  assert.equal(result.request.effect_id, context.effect);
});
test('edit reads authorized target then sends exact expected snapshot', async () => {
  const calls = [], current = { number: 7, title: 'Old', body: 'marker\nOld', base: 'main',
    head: { repository: context.repository, branch: 'branch', sha: 'a'.repeat(40) } };
  await execute(['pr', 'edit', '7', '--title', 'New', '--body', body], context, {
    mediate: request => { calls.push(request); return { state: 'confirmed', result: current }; } });
  assert.equal(calls.length, 2);
  assert.equal(calls[0].operation, 'pr_read');
  assert.deepEqual(calls[1].payload.expected, { title: current.title, body: current.body, head_sha: current.head.sha });
  assert.equal(calls[1].effect_id, 'effect-1');
  assert.equal(calls[1].payload.body, body);
});
test('unknown write makes one call and is never retried', async () => {
  let count = 0;
  await assert.rejects(execute(['pr', 'create', '--title', 'Title', '--body', body, '--head', 'branch', '--base', 'main'], context,
    { mediate: () => { count++; return { state: 'unknown' }; } }), failure => failure.exit === 4);
  assert.equal(count, 1);
});
test('unsupported syntax and missing identity make zero calls', async () => {
  const commands = [['auth', 'token'], ['api', 'graphql'], ['api', 'repos/other/repo/issues'],
    ['api', 'repos/example/disposable/issues', '--method', 'POST'], ['pr', 'view', '7', '--json', 'body'],
    ['run', 'list', '--repo', 'other/repo'], ['pr', 'view', '7', '--repo', context.repository, '--repo', context.repository],
    ['issue', 'create'], ['extension', 'exec', 'x'], ['api', 'repos/example/disposable/../issues'],
    ['api', 'repos/example/disposable/issues?per_page=100']];
  let count = 0;
  for (const command of commands) await assert.rejects(execute(command, context, {
    mediate: () => { count++; }, readBody: () => { throw new Error('unexpected body read'); } }), AdapterError);
  await assert.rejects(execute(['pr', 'create', '--title', 'x', '--body', body, '--head', 'b', '--base', 'main'],
    { ...context, effect: undefined }, { mediate: () => { count++; } }), /durable_effect_required/);
  assert.equal(count, 0);
});
test('ambient token environment neither authorizes nor changes requests', () => {
  const before = plan(['pr', 'view', '7'], context);
  const old = process.env.GH_TOKEN;
  try { process.env.GH_TOKEN = 'synthetic-ambient-must-not-be-used';
    assert.deepEqual(plan(['pr', 'view', '7'], context), before); }
  finally { if (old === undefined) delete process.env.GH_TOKEN; else process.env.GH_TOKEN = old; }
});
test('denial and unknown have different exit categories', async () => {
  for (const [response, exit] of [[{ error: 'grant_unavailable' }, 3], [{ state: 'unknown' }, 4]])
    await assert.rejects(execute(['pr', 'view', '7'], context, { mediate: () => response }), failure => failure.exit === exit);
});
