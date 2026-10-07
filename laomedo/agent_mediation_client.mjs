// Run-scoped mediator client. The provider credential remains in the host service.
// Usage: printf '%s' '{"repository":"owner/repo","operation":"actions_read","payload":{}}' |
//   node /run/laomedo/mediate.mjs
import { readFile } from 'node:fs/promises';

const url = process.env.LAOMEDO_MEDIATOR_URL;
const capabilityFile = process.env.LAOMEDO_CAPABILITY_FILE;
if (!url || !capabilityFile || !/^http:\/\/host\.docker\.internal:\d+\/v1\/mediate$/.test(url)) {
  process.stderr.write('mediation endpoint unavailable\n');
  process.exit(2);
}

try {
  let body = '';
  for await (const chunk of process.stdin) {
    body += chunk;
    if (body.length > 1024 * 1024) throw new Error('request too large');
  }
  const request = JSON.parse(body);
  if (!request || typeof request !== 'object' || Array.isArray(request)) {
    throw new Error('invalid request');
  }
  const capability = (await readFile(capabilityFile, 'utf8')).trim();
  if (!capability) throw new Error('capability unavailable');
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'authorization': `Bearer ${capability}`, 'content-type': 'application/json' },
    body: JSON.stringify(request),
    signal: AbortSignal.timeout(15000),
  });
  const result = await response.text();
  process.stdout.write(result + '\n');
  if (!response.ok) process.exitCode = 1;
} catch {
  // Never print the capability, request body, or provider response on error.
  process.stderr.write('mediation request failed\n');
  process.exitCode = 2;
}
