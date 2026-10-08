// Network-free run-scoped mediation client. The host bridge holds the grant.
// CLI: node /run/laomedo/mediate.mjs --request-file /draft/request.json
import { readFile, rename, writeFile } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
import { fileURLToPath } from 'node:url';

const workspace = '/draft';
const responses = '/run/laomedo/responses';

export async function mediate(request) {
  const body = JSON.stringify(request);
  if (Buffer.byteLength(body, 'utf8') > 1024 * 1024) throw new Error('request_too_large');
  const effectId = request?.effect_id;
  if (typeof effectId !== 'string' ||
      !/^[a-z0-9][a-z0-9._-]{0,63}$/.test(effectId)) {
    throw new Error('effect_id_invalid');
  }
  const finalPath = `${workspace}/.laomedo-req-${effectId}.json`;
  const pending = `${workspace}/.laomedo-req-${effectId}.${randomUUID()}.pending`;
  await writeFile(pending, body, { encoding: 'utf8', flag: 'wx', mode: 0o600 });
  await rename(pending, finalPath);
  const responsePath = `${responses}/${effectId}.json`;
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    try {
      return JSON.parse(await readFile(responsePath, 'utf8'));
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }
  throw new Error('response_timeout');
}

if (process.argv[1] && fileURLToPath(import.meta.url) === process.argv[1]) {
  try {
    if (process.argv.length !== 4 || process.argv[2] !== '--request-file' ||
        !/^\/draft\/[a-z0-9][a-z0-9._-]{0,63}\.json$/.test(process.argv[3])) {
      throw new Error('request_path_invalid');
    }
    const body = await readFile(process.argv[3], 'utf8');
    if (Buffer.byteLength(body, 'utf8') > 1024 * 1024) throw new Error('request_too_large');
    const result = await mediate(JSON.parse(body));
    process.stdout.write(JSON.stringify(result) + '\n');
    if (result.state !== 'confirmed') process.exitCode = 1;
  } catch (error) {
    // Never print request content or host paths on an error.
    const codes = new Set(['EACCES', 'EPERM', 'ENOENT', 'EEXIST', 'ETIMEDOUT']);
    const code = codes.has(error?.code) ? error.code :
      error?.message === 'response_timeout' ? 'response_timeout' : 'client_error';
    process.stderr.write(`mediation response unavailable: ${code}\n`);
    process.exitCode = 2;
  }
}
