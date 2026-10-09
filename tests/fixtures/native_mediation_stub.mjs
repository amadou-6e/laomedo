// A synthetic client stub, not acceptance evidence of the production mediator.
import { readFileSync, appendFileSync } from 'node:fs';
let input = '';
for await (const chunk of process.stdin) input += chunk;
const request = JSON.parse(input), commit = readFileSync('/tmp/commit','utf8');
appendFileSync('/tmp/client-journal', JSON.stringify(request)+'\n');
let result;
if (request.repository !== 'example/disposable') throw Error('repository_mismatch');
if (request.operation === 'git_fetch') result = request.payload.action === 'list' ?
  {refs:[{ref:'refs/heads/main',commit}]} :
  {ref:request.payload.ref,commit,bundle:readFileSync('/tmp/read.bundle').toString('base64')};
else if (request.operation === 'bundle_freeze') result = {status:'frozen'};
else if (request.operation === 'bundle_status') result = {...request.payload,stage_digest:'synthetic'};
else if (request.operation === 'git_push') result = {branch:request.payload.branch,commit};
else if (request.operation === 'pr_read') result = {number:7};
else throw Error('unsupported_operation');
process.stdout.write(JSON.stringify({state:'confirmed',result})+'\n');
