const net = require('node:net');

const socket = net.connect(443, 'chatgpt.com');
socket.setTimeout(10000);
socket.on('connect', () => {
  process.stdout.write('tcp_reachable');
  socket.end();
});
socket.on('error', (error) => {
  process.stderr.write(error.code || error.name);
  process.exitCode = 1;
});
socket.on('timeout', () => {
  process.stderr.write('timeout');
  socket.destroy();
  process.exitCode = 1;
});
