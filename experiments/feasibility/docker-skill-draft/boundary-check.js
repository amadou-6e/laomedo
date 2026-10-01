const fs = require('node:fs');

const target = '/store/sentinel.txt';
fs.writeSync(1, `attempted_path=${target}\n`);
try {
  fs.writeFileSync(target, 'FORBIDDEN');
  fs.writeSync(1, 'result=unexpected_write_success\n');
  process.exitCode = 3;
} catch (error) {
  fs.writeSync(1, `result=denied error=${error.code || error.name}\n`);
  process.exitCode = 2;
}
