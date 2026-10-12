// Experiment-only mediation transport. No shell network or provider credential.
import { readFile, writeFile, rename, unlink } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';
const root = '/draft/.git/laomedo-mediation';
const id = randomUUID();
try {
  let body = '';
  for await (const part of process.stdin) {
    body += part;
    if (Buffer.byteLength(body) > 1024 * 1024) throw new Error('oversize');
  }
  const value = JSON.parse(body);
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('invalid');
  await writeFile(`${root}/${id}.pending`, JSON.stringify(value), { flag: 'wx', mode: 0o600 });
  await rename(`${root}/${id}.pending`, `${root}/${id}.request`);
  const deadline = Date.now() + 17000;
  while (Date.now() < deadline) {
    try {
      const response = JSON.parse(await readFile(`${root}/${id}.response`, 'utf8'));
      await unlink(`${root}/${id}.response`);
      if (typeof response.body !== 'string' || !Number.isInteger(response.status)) throw new Error('invalid');
      process.stdout.write(response.body + '\n');
      process.exitCode = response.status >= 200 && response.status < 300 ? 0 : 1;
      break;
    } catch (error) {
      if (error.code !== 'ENOENT') throw error;
      await new Promise(resolve => setTimeout(resolve, 50));
    }
  }
  if (process.exitCode === undefined) throw new Error('timeout');
} catch {
  process.stderr.write('mediation request failed\n');
  process.exitCode = 2;
}
