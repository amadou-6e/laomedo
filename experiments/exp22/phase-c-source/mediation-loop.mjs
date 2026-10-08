// Bounded fake-write loop. The host may kill this process before it finishes.
// It never prints the bearer or request body.
import { spawnSync } from 'node:child_process';

for (let index = 0; index < 120; index += 1) {
  const body = JSON.stringify({
    repository: 'example/disposable',
    operation: 'pr_update',
    payload: { number: 7, head: 'phase-c-b', base: 'main', marker: 'phase-c' },
    effect_id: `phase-c-kill-${index}`,
  });
  const call = spawnSync('node', ['/run/laomedo/mediate.mjs'], {
    input: body, encoding: 'utf8', timeout: 20000,
  });
  let state = 'unreadable';
  try { state = JSON.parse(call.stdout).state ?? 'missing'; } catch { /* no body */ }
  process.stdout.write(JSON.stringify({
    index, at_wall_ms: Date.now(), at_monotonic_ms: performance.now(),
    exit_code: call.status, state,
  }) + '\n');
  await new Promise(resolve => setTimeout(resolve, 500));
}

