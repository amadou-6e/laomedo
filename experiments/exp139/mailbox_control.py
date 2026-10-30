"""No-model, no-provider control for prospective file-based mediation transport."""
import json
from pathlib import Path
import subprocess
import tempfile
from experiments.exp139.settings import PROFILE_OVERRIDES
from experiments.exp139.helper_control import IMAGE; from experiments.exp139.helper_control import ROOT

SCRIPT = r'''
const fs=require('fs'), cp=require('child_process'), http=require('http');
let calls=0, paths=[], operations=[];
const server=http.createServer((q,r)=>{
 calls++;paths.push(q.url);let text='';q.on('data',v=>text+=v);q.on('end',()=>{
 const request=JSON.parse(text);operations.push(request.operation);
 const result=['bundle_status','git_push'].includes(request.operation)?{commit:request.payload.commit,branch:request.payload.branch,stage_attempt_id:request.payload.stage_attempt_id}:{fixture:true};
 r.writeHead(200);r.end(JSON.stringify({state:'confirmed',result}));});
});
server.listen(0,'127.0.0.1',async()=>{
 cp.execFileSync('git',['init','--template=','-b','fixture-branch','/draft']);
 cp.execFileSync('git',['-C','/draft','remote','add','origin','laomedo::fixture/repo']);
 const relay=cp.spawn('node',['/run/laomedo/relay.mjs'],{env:{...process.env,LAOMEDO_MEDIATOR_URL:`http://host.docker.internal:${server.address().port}/v1/mediate`,LAOMEDO_MEDIATOR_INSTANCE:'0'.repeat(32)},stdio:'ignore'});
 const directory='/draft/.git/laomedo-mediation';
 const wait=()=>new Promise(r=>setTimeout(r,25));
 for(let n=0;n<100&&!fs.existsSync(directory+'/ready');n++)await wait();
 if(!fs.existsSync(directory+'/ready'))throw Error('relay_startup');
 const cases=[
 ['helper', 'git --exec-path > /draft/helper-result'],
 ['client', 'printf \'%s\' \'{"repository":"fixture/repo","operation":"fixture_read","payload":{}}\' | node /run/laomedo/mediate.mjs > /draft/client-result'],
 ['push', 'set -e; git config user.name Fixture; git config user.email fixture@example.invalid; printf fixture > report.txt; git add report.txt; git commit -m fixture >/draft/commit-stdout; git push origin HEAD:refs/heads/fixture-branch >/draft/push-stdout 2>/draft/push-stderr; printf PUSH_CONFIRMED > /draft/push-result'],
 ['network', `node -e "require('http').get('http://127.0.0.1:${server.address().port}/forbidden',r=>{require('fs').writeFileSync('/draft/network-result','REACHED');r.resume()}).on('error',e=>require('fs').writeFileSync('/draft/network-result',e.code))"`],
 ['auth', 'node -e "try {require(\'fs\').readFileSync(\'/home/runner/.codex/auth.json\');require(\'fs\').writeFileSync(\'/draft/auth-result\',\'READ\')} catch(e) {require(\'fs\').writeFileSync(\'/draft/auth-result\',e.code)}"']
 ];
 const results=[];
 for(const [name,command]of cases){
  await new Promise(done=>{const p=cp.spawn('codex',[...JSON.parse(process.env.ARGS),'sandbox','-P','container-edit','--','bash','-lc',command],{stdio:'ignore',cwd:'/draft'});p.on('close',exit=>{let result;try{result=fs.readFileSync('/draft/'+name+'-result','utf8')}catch{result='absent'}results.push({name,exit,result});done()})});
 }
 const id='11111111-1111-1111-1111-111111111111';
 fs.writeFileSync('/draft/canary','UNTOUCHED');fs.symlinkSync('/draft/canary',directory+'/'+id+'.request');
 for(let n=0;n<100&&!fs.existsSync(directory+'/'+id+'.response');n++)await wait();
 results.push({name:'symlink_request',status:JSON.parse(fs.readFileSync(directory+'/'+id+'.response','utf8')).status,unchanged:fs.readFileSync('/draft/canary','utf8')==='UNTOUCHED'});
 const fifo='22222222-2222-2222-2222-222222222222';
 cp.execFileSync('mkfifo',[directory+'/'+fifo+'.request']);
 for(let n=0;n<100&&!fs.existsSync(directory+'/'+fifo+'.response');n++)await wait();
 results.push({name:'fifo_request',status:JSON.parse(fs.readFileSync(directory+'/'+fifo+'.response','utf8')).status});
 fs.renameSync(directory,directory+'-old');fs.mkdirSync(directory);
 fs.writeFileSync(directory+'/33333333-3333-3333-3333-333333333333.request','{}');
 await new Promise(r=>setTimeout(r,150));
 results.push({name:'directory_replacement',ignored:!fs.existsSync(directory+'/33333333-3333-3333-3333-333333333333.response')});
 relay.kill();server.close();console.log(JSON.stringify({results,calls,paths,operations,bundle_present:fs.existsSync('/draft/.laomedo-handoff.bundle')}));
});
'''


def probe():
    with tempfile.TemporaryDirectory(prefix='laomedo139-mailbox-') as temporary:
        root=Path(temporary)
        (root/'config.toml').write_bytes((ROOT/'src/laomedo/agents/agents/codex/resources/runner-config.toml').read_bytes())
        (root/'fixture.cjs').write_text(SCRIPT,encoding='utf-8')
        (root/'capability').write_text('DUMMY_RUN_CAPABILITY')
        (root/'auth.json').write_text('{"dummy":"NOT_A_LOGIN"}')
        (root/'bin').mkdir()
        (root/'bin/git-remote-laomedo').write_text('#!/bin/sh\nexec node /run/laomedo/git-remote.mjs "$@"\n',newline='\n')
        args=['docker','run','--rm','--pull=never','--network','none',
              '--add-host','host.docker.internal:127.0.0.1','--user','10001:10001',
              '--cap-drop','ALL','--security-opt','no-new-privileges',
              '--tmpfs','/draft:rw,mode=1777',
              '--mount',f'type=bind,source={root},target=/fixture,readonly',
              '--mount',f'type=bind,source={root / "capability"},target=/run/laomedo/capability,readonly',
              '--mount',f'type=bind,source={root / "bin"},target=/run/laomedo/bin,readonly',
              '--mount',f'type=bind,source={Path(__file__).with_name("mailbox_client.mjs")},target=/run/laomedo/mediate.mjs,readonly',
              '--mount',f'type=bind,source={Path(__file__).with_name("mailbox_relay.mjs")},target=/run/laomedo/relay.mjs,readonly',
              '--mount',f'type=bind,source={ROOT / "laomedo/agent_git_remote.mjs"},target=/run/laomedo/git-remote.mjs,readonly',
              '--env','LAOMEDO_REPOSITORY=fixture/repo','--env','LAOMEDO_RUN_BRANCH=fixture-branch',
              '--env','LAOMEDO_MEDIATION_FILE_STDIO=1',
              '--env','GIT_CONFIG_COUNT=1','--env','GIT_CONFIG_KEY_0=safe.directory','--env','GIT_CONFIG_VALUE_0=/draft',
              '--env','GIT_EXEC_PATH=/run/laomedo/bin','--env','ARGS='+json.dumps(PROFILE_OVERRIDES),
              '--workdir','/draft','--entrypoint','sh',IMAGE,'-c',
              'mkdir -p /home/runner/.codex; cp /fixture/config.toml /home/runner/.codex/config.toml; '
              'cp /fixture/auth.json /home/runner/.codex/auth.json; export CODEX_HOME=/home/runner/.codex; exec node /fixture/fixture.cjs']
        process=subprocess.run(args,capture_output=True,timeout=35)
        if process.returncode: raise ValueError('mailbox_fixture_failed')
        result=json.loads(process.stdout.decode().splitlines()[-1])
        expected={row['name']:row for row in result['results']}
        assert expected['helper']['result'].strip()=='/run/laomedo/bin'
        assert json.loads(expected['client']['result'])['state']=='confirmed'
        assert expected['push']['exit']==0 and expected['push']['result']=='PUSH_CONFIRMED'
        assert expected['network']['result']=='EPERM'
        assert expected['auth']['result'] in {'EPERM','EACCES'}
        assert expected['symlink_request']['status']==400 and expected['symlink_request']['unchanged']
        assert expected['fifo_request']['status']==400
        assert expected['directory_replacement']['ignored']
        assert result['calls']==4 and result['paths']==['/v1/mediate']*4
        assert result['operations']==['fixture_read','bundle_freeze','bundle_status','git_push']
        assert result['bundle_present']
        return {'controls':result,'model_turns':0,'provider_writes':0,'network':'none','credential_fixture':'dummy_only'}


if __name__=='__main__':
    result=probe()
    Path(__file__).with_name('MAILBOX-CONTROL.json').write_text(json.dumps(result,indent=2,sort_keys=True)+'\n')
    print(json.dumps(result))
