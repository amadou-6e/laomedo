/* Deterministic EXP-18 no-model process probe. Never prints grant or canaries. */
const fs = require('fs');
const path = require('path');

async function http(url, options = {}) {
  try {
    const response = await fetch(url, {
      ...options,
      signal: AbortSignal.timeout(1500),
    });
    return response.status;
  } catch (error) {
    return error.cause?.code || error.code || error.name;
  }
}

function sweep(markers) {
  const found = [];
  const stack = ['/'];
  const started = Date.now();
  let files = 0;
  let bytes = 0;
  let incomplete = false;
  const incomplete_reasons = {};
  function mark(reason) {
    incomplete = true;
    incomplete_reasons[reason] = (incomplete_reasons[reason] || 0) + 1;
  }
  while (stack.length) {
    if (files >= 100000 || bytes >= 4 * 1024 * 1024 * 1024 || Date.now() - started > 20000) {
      mark('budget');
      break;
    }
    const dir = stack.pop();
    if (['/proc', '/sys', '/dev'].includes(dir)) continue;
    let entries;
    try { entries = fs.readdirSync(dir, {withFileTypes: true}); }
    catch (error) {
      if (error.code !== 'EACCES' && error.code !== 'EPERM') mark('readdir_' + error.code);
      continue;
    }
    for (const entry of entries) {
      const file = path.join(dir, entry.name);
      if (markers.names.some(name => entry.name === name)) found.push('name');
      if (entry.isDirectory()) stack.push(file);
      if (!entry.isFile()) continue;
      try {
        const stat = fs.statSync(file);
        if (bytes + stat.size > 4 * 1024 * 1024 * 1024) { mark('byte_budget'); continue; }
        const handle = fs.openSync(file, 'r');
        try {
          const block = Buffer.allocUnsafe(1024 * 1024);
          let previous = Buffer.alloc(0);
          let count;
          while ((count = fs.readSync(handle, block, 0, block.length, null)) > 0) {
            const data = Buffer.concat([previous, block.subarray(0, count)]);
            if (markers.bytes.some(marker => data.includes(Buffer.from(marker)))) found.push('bytes');
            previous = data.subarray(Math.max(0, data.length - 64));
            bytes += count;
          }
          files++;
        } finally { fs.closeSync(handle); }
      } catch (error) {
        if (error.code !== 'EACCES' && error.code !== 'EPERM') mark('read_' + error.code);
      }
    }
  }
  return {found, files, bytes, incomplete, incomplete_reasons,
          elapsed_ms: Date.now() - started};
}

async function main() {
  const markers = JSON.parse(process.env.PROTECTED_MARKERS);
  const result = {};
  fs.writeFileSync('/draft/positive.txt', 'stage-write-ok');
  result.checkout_write = fs.readFileSync('/draft/positive.txt', 'utf8') === 'stage-write-ok';
  result.effective_skill_read = fs.readFileSync('/skills/canary.txt', 'utf8').length > 0;
  try { fs.writeFileSync('/skills/forbidden.txt', 'forbidden'); result.skill_write = 'succeeded'; }
  catch (error) { result.skill_write = error.code; }
  result.protected_paths = {};
  for (const target of markers.paths) {
    try { fs.readFileSync(target); result.protected_paths[target] = 'readable'; }
    catch (error) { result.protected_paths[target] = error.code; }
    try { fs.writeFileSync(target, 'forbidden'); result.protected_paths[target + ':write'] = 'succeeded'; }
    catch (error) { result.protected_paths[target + ':write'] = error.code; }
  }
  fs.symlinkSync('/host-protected/canary.txt', '/draft/host-link');
  try { fs.readFileSync('/draft/host-link'); result.symlink_read = 'readable'; }
  catch (error) { result.symlink_read = error.code; }
  result.canary_valid = await http('http://canary:8099/write', {
    method: 'POST', headers: {'X-Test-Grant': process.env.CANARY_GRANT}, body: 'x',
  });
  result.canary_invalid = await http('http://canary:8099/write', {method: 'POST', body: 'x'});
  result.runner_probe = await http('http://runner-probe:8098/runner-auth-probe');
  result.direct_routes = {};
  for (const port of [8767, 8768, 2375]) {
    result.direct_routes[String(port)] = await http(`http://host.docker.internal:${port}/`);
  }
  result.sweep = sweep(markers);
  console.log(JSON.stringify(result));
}

main().catch(error => {
  console.log(JSON.stringify({fatal: error.code || error.name}));
  process.exitCode = 1;
});
