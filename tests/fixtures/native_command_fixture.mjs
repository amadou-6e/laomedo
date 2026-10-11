// Development protocol fixture: no host mediator, provider credential, or model.
import { execFileSync } from 'node:child_process';
import { mkdirSync, writeFileSync, readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
const call = (args, cwd = '/tmp/source') => execFileSync('git', args, {cwd, encoding:'utf8', timeout:15000}).trim();
mkdirSync('/tmp/source');
call(['init','--quiet','-b','main']);
writeFileSync('/tmp/source/file','native fixture\n');
call(['add','file']);
call(['-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','--quiet','-m','fixture']);
const commit = call(['rev-parse','HEAD']);
call(['branch','laomedo-read']);
call(['bundle','create','/tmp/read.bundle','refs/heads/laomedo-read']);
writeFileSync('/tmp/commit', commit);
mkdirSync('/tmp/agent');
call(['init','--quiet','-b','run-branch'], '/tmp/agent');
call(['remote','add','origin','laomedo::example/disposable'], '/tmp/agent');
call(['fetch','origin'], '/tmp/agent');
assert.equal(call(['rev-parse','refs/remotes/origin/main'], '/tmp/agent'), commit);
call(['reset','--hard',commit], '/tmp/agent');
call(['push','origin','HEAD:refs/heads/run-branch'], '/tmp/agent');
call(['push','origin','HEAD:refs/heads/run-branch'], '/tmp/agent');
for (const args of [['push','origin','+HEAD:refs/heads/run-branch'],
                    ['push','origin','HEAD:refs/heads/other']]) {
  assert.throws(() => call(args, '/tmp/agent'));
}
const read = JSON.parse(execFileSync('gh',['pr','view','7'], {encoding:'utf8'}));
assert.equal(read.number,7);
assert.throws(() => execFileSync('gh',['auth','token'], {encoding:'utf8'}));
const journal = readFileSync('/tmp/client-journal','utf8').trim().split('\n').map(JSON.parse);
assert.equal(journal.filter(item => item.operation === 'bundle_freeze').length,1);
assert.equal(journal.filter(item => item.operation === 'git_push').length,2);
assert(journal.filter(item => item.operation === 'git_push').every(item => item.effect_id === journal.find(item => item.operation === 'git_push').effect_id));
process.stdout.write(JSON.stringify({native_fetch:true,native_push:true,repeated_identity:true,gh_read:true,unsupported_denied:true,host_provider_verified:false})+'\n');
