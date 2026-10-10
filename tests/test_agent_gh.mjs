import assert from 'node:assert/strict';
import test from 'node:test';
import { execute, plan, readBody, AdapterError, ISSUE_GRAPHQL_QUERY } from '../laomedo/agent_gh_adapter.mjs';
import { mkdtempSync, writeFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const context = { repository: 'example/disposable', effect: 'effect-1', marker: 'marker' };
const body = 'marker\r\nUnicode: λ\n';
test('fixed GraphQL read maps only to the selected issue-list grant and fields', async () => {
  const input = { query: ISSUE_GRAPHQL_QUERY, variables: { owner: 'example', name: 'disposable' } };
  const calls = [], args = ['api', 'graphql', '--method', 'POST', '--input', '-'];
  const result = await execute(args, context, { readBody: () => JSON.stringify(input),
    mediate: request => { calls.push(request); return { state: 'confirmed',
      result: { items: [{ number: 7, title: 'T', body: 'B', extra: 'not selected' }] } }; } });
  assert.deepEqual(calls, [{ repository: context.repository, operation: 'issue_list',
    payload: { format: 'fixed_graphql' } }]);
  assert.deepEqual(result, { data: { repository: { issues: { nodes: [{ number: 7, title: 'T', body: 'B' }] } } } });
  for (const items of [[{ number: true, title: 'T', body: 'B' }], [{ number: 7, title: 'T', body: null }],
    [{ number: 7, title: 'T', body: 'B', pull_request: {} }], Array(31).fill({ number: 7, title: 'T', body: 'B' })]) {
    await assert.rejects(execute(args, context, { readBody: () => JSON.stringify(input),
      mediate: () => ({ state: 'confirmed', result: { items } }) }), /graphql_readback_invalid/);
  }
});
test('fixed GraphQL refuses mutations fragments variables and extra selections before mediation', async () => {
  let calls = 0;
  const input = { query: ISSUE_GRAPHQL_QUERY, variables: { owner: 'example', name: 'disposable' } };
  const variations = [{ ...input, query: 'mutation {createIssue{issue{number}}}' },
    { ...input, query: ISSUE_GRAPHQL_QUERY + ' fragment F on Issue{url}' },
    { ...input, query: ISSUE_GRAPHQL_QUERY.replace('number title body', 'number title body url') },
    { ...input, variables: { owner: 'other', name: 'repo' } },
    { ...input, variables: { ...input.variables, extra: 'x' } }, { ...input, operationName: 'x' }, null];
  for (const value of variations) {
    await assert.rejects(execute(['api', 'graphql', '--method', 'POST', '--input', '-'], context,
      { readBody: () => JSON.stringify(value), mediate: () => { calls++; } }), AdapterError);
  }
  assert.equal(calls, 0);
});
test('issue view uses fixed selected REST read and rejects a PR or mismatched identity', async () => {
  const calls = [];
  const args = ['issue', 'view', '7'];
  const deps = { mediate: request => { calls.push(request);
    return { state: 'confirmed', result: { number: 7, title: 'Issue' } }; } };
  assert.equal((await execute(args, context, deps)).number, 7);
  assert.deepEqual(calls[0], { repository: context.repository, operation: 'api_rest_read',
    payload: { method: 'GET', path: '/repos/example/disposable/issues/7' } });
  for (const result of [{ number: 8 }, { number: 7, pull_request: {} }, null]) {
    await assert.rejects(execute(args, context, { mediate: () => ({ state: 'confirmed', result }) }),
      /issue_readback_invalid/);
  }
});
test('issue create carries review identity without granting or trusting it', async () => {
  const args = ['issue', 'create', '--title', 'Title', '--body-file', '-'];
  const planned = plan(args, { ...context, reviewedProposal: 'review-7' }, () => body);
  assert.deepEqual(planned.request, { repository: context.repository, operation: 'issue_create',
    payload: { title: 'Title', body, marker: 'marker', reviewed_proposal_id: 'review-7' }, effect_id: 'effect-1' });
  let calls = 0;
  await assert.rejects(execute(args, context, { readBody: () => body, mediate: () => { calls++; } }),
    /reviewed_proposal_required/);
  assert.equal(calls, 0);
  await assert.rejects(execute(args, { ...context, reviewedProposal: 'review-7' }, {
    readBody: () => body, mediate: () => ({ error: 'issue_review_denied' }) }), failure => failure.exit === 3);
});
test('classified API POST is identical to the authorized PR create request', () => {
  const input = { title: 'Title', body, head: 'branch', base: 'main' };
  const viaApi = plan(['api', 'repos/example/disposable/pulls', '--method', 'POST', '--input', '-'],
    context, file => { assert.equal(file, '-'); return JSON.stringify(input); });
  const viaPr = plan(['pr', 'create', '--title', input.title, '--body', body, '--head', input.head,
    '--base', input.base], context);
  assert.deepEqual(viaApi, viaPr);
});
test('classified API POST refuses wider operations and malformed bodies before mediation', async () => {
  let calls = 0;
  const args = ['api', 'repos/example/disposable/pulls', '--method', 'POST', '--input', 'body.json'];
  for (const input of ['[]', '{}', 'null', '{', JSON.stringify({ title: 'T', body, head: 'b', base: 'main', draft: true }),
    JSON.stringify({ title: 'T', body: 'missing', head: 'b', base: 'main' }),
    JSON.stringify({ title: 'T', body, head: 42, base: 'main' })]) {
    await assert.rejects(execute(args, context, { readBody: () => input, mediate: () => { calls++; } }), AdapterError);
  }
  for (const path of ['repos/other/repo/pulls', 'repos/example/disposable/issues',
    'repos/example/disposable/pulls/7', 'graphql']) {
    await assert.rejects(execute(['api', path, '--method', 'POST', '--input', '-'], context, {
      readBody: () => { throw new Error('unexpected body read'); }, mediate: () => { calls++; }
    }), AdapterError);
  }
  await assert.rejects(execute(args, { ...context, effect: undefined }, {
    readBody: () => { throw new Error('unexpected body read'); }, mediate: () => { calls++; }
  }), /durable_effect_required/);
  assert.equal(calls, 0);
});
test('classified API POST preserves single-dispatch unknown and grant denials', async () => {
  const calls = [], args = ['api', 'repos/example/disposable/pulls', '--method', 'POST', '--input', '-'];
  const dependencies = { readBody: () => JSON.stringify({ title: 'T', body, head: 'b', base: 'main' }),
    mediate: request => { calls.push(request); return { state: 'unknown' }; } };
  await assert.rejects(execute(args, context, dependencies), failure => failure.exit === 4);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].operation, 'pr_create');
  await assert.rejects(execute(args, context, { ...dependencies,
    mediate: () => ({ error: 'operation_denied' }) }), failure => failure.exit === 3);
});
test('explicit same-repository list forms map to read-only operations', async () => {
  const calls = [];
  for (const [noun, operation] of [['pr', 'pr_list'], ['issue', 'issue_list']]) {
    const output = await execute([noun, 'list', '--repo', context.repository], context, {
      mediate: request => { calls.push(request); return { state: 'confirmed', result: { items: [{ number: 7 }] } }; }
    });
    assert.deepEqual(output, { items: [{ number: 7 }] });
    assert.deepEqual(calls.at(-1), { repository: context.repository, operation, payload: {} });
  }
  assert.equal(calls.length, 2);
});
test('list refuses wider repositories, positional targets and paging before mediation', async () => {
  let calls = 0;
  for (const noun of ['pr', 'issue']) {
    for (const tail of [['7'], ['--repo', 'other/repo'], ['--limit', '100'], ['--state', 'all']]) {
      await assert.rejects(execute([noun, 'list', ...tail], context, {
        mediate: () => { calls++; }
      }), AdapterError);
    }
    await assert.rejects(execute([noun, 'list'], context, {
      mediate: () => ({ error: 'operation_denied' })
    }), failure => failure.exit === 3);
  }
  assert.equal(calls, 0);
});
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
test('empty repository flag is refused', () => {
  assert.throws(() => plan(['pr', 'view', '7', '--repo', ''], context), /unsupported_syntax/);
});
test('real body reader preserves BOM and rejects oversized files', () => {
  const directory = mkdtempSync(join(tmpdir(), 'laomedo-cli-test-'));
  try {
    const path = join(directory, 'body');
    const bytes = Buffer.from('\ufeffmarker\r\nλ\n', 'utf8');
    writeFileSync(path, bytes);
    assert.deepEqual(Buffer.from(readBody(path), 'utf8'), bytes);
    writeFileSync(path, Buffer.alloc(65537, 97));
    assert.throws(() => readBody(path), /body_file_invalid/);
  } finally { rmSync(directory, { recursive: true }); }
});
test('repeated unknown create never invents an effect', async () => {
  const calls = [];
  const dependencies = { mediate: request => { calls.push(request); return { state: 'unknown' }; } };
  for (let i = 0; i < 2; i++) await assert.rejects(execute(['pr', 'create', '--title', 'Title', '--body', body,
    '--head', 'branch', '--base', 'main'], context, dependencies), failure => failure.exit === 4);
  assert.deepEqual(calls[0], calls[1]);
});
test('repeated unknown edit retains conflict code, no replacement identity', async () => {
  const writes = [];
  let read = 0;
  const dependencies = { mediate: request => {
    if (request.operation === 'pr_read') return { state: 'confirmed', result: {
      number: 7, title: 'Title', body: 'marker current ' + read++, base: 'main',
      head: { repository: context.repository, branch: 'branch', sha: 'a'.repeat(40) } } };
    writes.push(request);
    return writes.length === 1 ? { state: 'unknown' } : { error: 'effect_conflict' };
  } };
  const args = ['pr', 'edit', '7', '--title', 'Title', '--body', body];
  await assert.rejects(execute(args, context, dependencies), failure => failure.exit === 4);
  await assert.rejects(execute(args, context, dependencies), /mediator_denied:effect_conflict/);
  assert.equal(writes.length, 2); // two explicit invocations, no internal retry
  assert.equal(writes[0].effect_id, writes[1].effect_id);
});
