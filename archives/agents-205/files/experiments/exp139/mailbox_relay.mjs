// Trusted experiment transport, started before Codex. Never evaluates a request.
import fs from 'node:fs';
import http from 'node:http';
const root = '/draft/.git/laomedo-mediation';
const flags = fs.constants;
const limit = 1024 * 1024;
const url = process.env.LAOMEDO_MEDIATOR_URL;
const instance = process.env.LAOMEDO_MEDIATOR_INSTANCE;
if (!/^http:\/\/host\.docker\.internal:\d+\/v1\/mediate$/.test(url ?? '') ||
    !/^[0-9a-f]{32}$/.test(instance ?? '')) process.exit(2);
fs.mkdirSync(root, { recursive: true, mode: 0o700 });
const directory = fs.openSync(root, flags.O_RDONLY | flags.O_DIRECTORY | flags.O_NOFOLLOW);
const anchored = `/proc/self/fd/${directory}`;
const capability = fs.readFileSync('/run/laomedo/capability', 'utf8').trim();
if (!capability) process.exit(2);
const seen = new Set();
function readRequest(name) {
  const fd = fs.openSync(`${anchored}/${name}`, flags.O_RDONLY | flags.O_NOFOLLOW | flags.O_NONBLOCK);
  try {
    const st = fs.fstatSync(fd);
    if (!st.isFile() || st.size > limit || st.nlink !== 1) throw new Error('invalid');
    // Bound allocation even if the agent changes the file after fstat.
    const buffer = Buffer.alloc(limit + 1);
    const count = fs.readSync(fd, buffer, 0, buffer.length, 0);
    if (count > limit) throw new Error('oversize');
    const value = JSON.parse(buffer.subarray(0, count).toString('utf8'));
    if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('invalid');
    return JSON.stringify(value);
  } finally { fs.closeSync(fd); }
}
function forward(body) {
  return new Promise(resolve => {
    let settled = false;
    const finish = value => { if (!settled) { settled = true; clearTimeout(timer); resolve(value); } };
    const rejected = { status: 502, body: '{"error":"relay_unavailable"}' };
    const req = http.request(url, { method: 'POST', headers: {
      authorization: `Bearer ${capability}`, 'content-type': 'application/json',
      'x-laomedo-mediator-instance': instance, 'content-length': Buffer.byteLength(body)
    } }, res => {
      const chunks = []; let size = 0;
      res.on('data', part => { size += part.length; if (size > limit) { res.destroy(); finish(rejected); } else chunks.push(part); });
      res.on('error', () => finish(rejected));
      res.on('end', () => finish({ status: res.statusCode, body: Buffer.concat(chunks).toString('utf8') }));
    });
    const timer = setTimeout(() => { req.destroy(); finish(rejected); }, 15000);
    req.on('error', () => finish(rejected));
    req.end(body);
  });
}
function respond(name, response) {
  const target = `${anchored}/${name.replace('.request', '.response')}`;
  const temporary = target + '.pending';
  let fd;
  try {
    fd = fs.openSync(temporary, flags.O_WRONLY | flags.O_CREAT | flags.O_EXCL | flags.O_NOFOLLOW, 0o600);
    fs.writeFileSync(fd, JSON.stringify(response));
    fs.closeSync(fd); fd = undefined;
    fs.linkSync(temporary, target); // Atomic delivery; never overwrite an existing target.
  } finally {
    if (fd !== undefined) fs.closeSync(fd);
    try { fs.unlinkSync(temporary); } catch { /* A tampered pending file stays unavailable. */ }
  }
}
// The fixed readiness file is created exclusively before untrusted execution.
fs.writeFileSync(`${anchored}/ready`, 'READY', { flag: 'wx', mode: 0o600 });
const deadline = Date.now() + 600000;
while (Date.now() < deadline && seen.size < 512) {
  for (const name of fs.readdirSync(anchored)) {
    if (seen.size >= 512) break;
    if (!/^[0-9a-f-]{36}\.request$/.test(name) || seen.has(name)) continue;
    seen.add(name);
    let response;
    try { response = await forward(readRequest(name)); }
    catch { response = { status: 400, body: '{"error":"relay_request_invalid"}' }; }
    try { respond(name, response); } catch { /* A replaced response path refuses delivery. */ }
  }
  await new Promise(resolve => setTimeout(resolve, 25));
}
fs.closeSync(directory);
