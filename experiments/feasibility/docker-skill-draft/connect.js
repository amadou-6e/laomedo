const fs = require('node:fs');
const net = require('node:net');

const host = process.argv[2];
const port = Number(process.argv[3]);
fs.writeSync(1, 'started\n');
const socket = net.connect({ host, port });
socket.setTimeout(8000);
socket.on('connect', () => {
  fs.writeSync(1, 'connected');
  socket.end();
});
socket.on('error', (error) => {
  fs.writeSync(2, error.code || error.name);
  process.exitCode = 1;
});
socket.on('timeout', () => {
  fs.writeSync(2, 'timeout');
  socket.destroy();
  process.exitCode = 1;
});
