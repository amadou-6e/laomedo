const fs=require('fs'),path=require('path'),cp=require('child_process');const {waitForPreview}=require('./preview_ready.cjs');
const {chromium}=require('C:/Users/Amadou/AppData/Local/Temp/lfui-dsby42ay/lf/src/frontend/node_modules/@playwright/test');
(async()=>{
 const e='C:/CodeWorkspace/laomedo/claude-review.local/agents-250-20261107',state=JSON.parse(fs.readFileSync(path.join(e,'runtime-path.json'))).path;
 const browser=await chromium.launch({channel:'msedge',headless:true});const results=[];
 try{const context=await browser.newContext({storageState:path.join(state,'browser-state.json')});
 await waitForPreview(context,'http://127.0.0.1:17863');const endpoint='http://127.0.0.1:17863/api/v1/laomedo/runner-service';
 for(let attempt=0;attempt<3;attempt++){
  const initial=await(await context.request.get(endpoint)).json();if(initial.state==='ready'){cp.execFileSync('C:/Users/Amadou/AppData/Local/Temp/lmi-be4oa1d0/Scripts/python.exe',['C:/CodeWorkspace/laomedo/.tools/continuous-exp/work/agents250-final/stop_codex.py'],{windowsHide:true,stdio:'pipe'});}else if(initial.state!=='offline')throw Error('initial_state_'+initial.state);
  const offline=await(await context.request.get(endpoint)).json();if(offline.state!=='offline')throw Error('not_offline');
  await new Promise(resolve=>setTimeout(resolve,2200));
  const checks=[context.request.get(endpoint),context.request.get(endpoint)];
  await new Promise(resolve=>setTimeout(resolve,1));
  const start=await(await context.request.post(endpoint+'/start')).json();
  const status=await Promise.all(checks.map(async request=>(await request).json()));
  results.push({attempt:attempt+1,start,concurrent_status:status,new_model_submissions:0});
  fs.writeFileSync(path.join(e,'real-start-race-fixed.json'),JSON.stringify(results,null,2));
  if(start.state==='prerequisite'&&start.reason==='runner_docker_check_unconfirmed'){console.log(JSON.stringify({dropped_start:true,...results.at(-1)}));break;}
  if(start.state!=='starting')throw Error('unexpected_start_state_'+start.state);
  const deadline=Date.now()+90000;let current;
  do{await new Promise(resolve=>setTimeout(resolve,500));current=await(await context.request.get(endpoint)).json();}while(current.state!=='ready'&&Date.now()<deadline);
  if(current.state!=='ready')throw Error('started_backend_not_ready');
  if(attempt===2)console.log(JSON.stringify({dropped_start:false,attempts:results.length}));
 }
 }finally{await browser.close();}
})().catch(error=>{console.error(error.message);process.exitCode=1});
