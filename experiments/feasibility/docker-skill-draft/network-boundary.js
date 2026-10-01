const fs = require('node:fs');
const net = require('node:net');
const { spawn } = require('node:child_process');

function command(args) {
  return new Promise((resolve) => {
    const child = spawn(args[0], args.slice(1), { stdio: ['ignore', 'pipe', 'pipe'] });
    let stdout = '';
    let stderr = '';
    child.stdout.on('data', (data) => { stdout += data.toString(); });
    child.stderr.on('data', (data) => { stderr += data.toString(); });
    child.on('close', (code) => resolve({
      code,
      started: stdout.includes('started'),
      connected: stdout.includes('connected'),
      stdout_excerpt: stdout.slice(0, 180),
      stderr_excerpt: stderr.slice(0, 180),
      error_class: stderr.includes('EPERM') ? 'EPERM'
        : stderr.includes('EACCES') ? 'EACCES'
        : stderr.includes('timeout') ? 'timeout'
        : stderr.includes('ENETUNREACH') ? 'ENETUNREACH'
        : stderr.includes('EAI_AGAIN') ? 'EAI_AGAIN'
        : stderr.includes('bwrap:') ? 'bubblewrap'
        : stderr ? 'other' : null,
    }));
    child.on('error', (error) => resolve({ code: null, connected: false,
      error_class: error.code || error.name }));
  });
}

async function main() {
  fs.mkdirSync('/home/runner/.codex', { recursive: true });
  fs.copyFileSync('/config.toml', '/home/runner/.codex/config.toml');
  const server = net.createServer((socket) => socket.end('fixture'));
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  const port = server.address().port;
  const direct = (host, targetPort) =>
    command(['node', '/probe/connect.js', host, String(targetPort)]);
  const sandbox = (host, targetPort) =>
    command(['codex', 'sandbox', '-P', 'container-test', '-C', '/draft', '--',
      'sh', '-c', `printf sandbox_entered; node /probe/connect.js ${host} ${targetPort}`]);
  const report = {
    credential_used: false,
    model_calls: 0,
    docker_network: 'bridge',
    sandbox_command_control: await command(['codex', 'sandbox', '-P',
      'container-test', '-C', '/draft', '--', 'sh', '-c', 'printf sandbox_entered']),
    sandbox_node_control: await command(['codex', 'sandbox', '-P',
      'container-test', '-C', '/draft', '--', 'node', '--version']),
    loopback_direct: await direct('127.0.0.1', port),
    loopback_sandboxed: await sandbox('127.0.0.1', port),
    external_direct: await direct('chatgpt.com', 443),
    external_sandboxed: await sandbox('chatgpt.com', 443),
  };
  server.close();
  report.boundary_passed = report.sandbox_command_control.code === 0
    && report.sandbox_command_control.stdout_excerpt.includes('sandbox_entered')
    && report.loopback_direct.connected
    && report.loopback_sandboxed.started
    && !report.loopback_sandboxed.connected
    && report.loopback_sandboxed.error_class === 'EPERM'
    && report.external_direct.connected
    && report.external_sandboxed.started
    && !report.external_sandboxed.connected
    && ['EPERM', 'EAI_AGAIN'].includes(report.external_sandboxed.error_class);
  process.stdout.write(`${JSON.stringify(report)}\n`);
  process.exitCode = report.boundary_passed ? 0 : 1;
}

main().catch((error) => {
  process.stderr.write(error.name);
  process.exitCode = 1;
});
