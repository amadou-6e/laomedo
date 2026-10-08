// Bounded fake-write loop. A runner-tree kill may interrupt one request.
// The host journal, not this file, is authoritative for effects.
import { appendFile } from 'node:fs/promises';
import { mediate } from '/run/laomedo/mediate.mjs';

for (let index = 0; index < 120; index += 1) {
  const effectId = `phase-c-kill-${index}`;
  const body = {
    repository: 'example/disposable', operation: 'pr_update',
    payload: { number: 8, head: 'phase-c-b', base: 'main', marker: 'phase-c' },
    effect_id: effectId,
  };
  let state = 'unknown';
  let error = null;
  try {
    const result = await mediate(body);
    state = result.state;
    error = typeof result.error === 'string' ? result.error : null;
  } catch {
    error = 'client_timeout_or_error';
  }
  await appendFile('/draft/loop.jsonl', JSON.stringify({
    index, effect_id: effectId, at_wall_ms: Date.now(), state, error,
  }) + '\n');
  if (state !== 'confirmed') break;
  await new Promise(resolve => setTimeout(resolve, 500));
}
