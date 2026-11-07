const fs=require('fs'),path=require('path');const {waitForPreview}=require('./preview_ready.cjs');
const {chromium,expect}=require('C:/Users/Amadou/AppData/Local/Temp/lfui-dsby42ay/lf/src/frontend/node_modules/@playwright/test');
(async()=>{
 const e='C:/CodeWorkspace/laomedo/claude-review.local/agents-250-20261107',state=JSON.parse(fs.readFileSync(path.join(e,'runtime-path.json'))).path,base='http://127.0.0.1:17863';
 const url=JSON.parse(fs.readFileSync(path.join(e,'live-graphs.json'))).find(g=>g.provider==='codex').url;
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try{const context=await browser.newContext({viewport:{width:1440,height:1000},storageState:path.join(state,'browser-state.json')}),page=await context.newPage();
  await waitForPreview(context,base);await page.goto(url);const node=page.locator('.react-flow__node[data-id="agent"]');await node.waitFor({timeout:90000});
  const original=await(await page.request.get(base+'/api/v1/laomedo/runner-service')).json();if(original.state!=='offline')throw Error('cancel_precondition_'+original.state);
  const before=fs.readdirSync(path.join(state,'codex/runs')).length;
  await node.getByRole('button',{name:'Run component',exact:true}).click();
  const popup=page.locator('[role="region"][data-error-code="runner_transport_failed"]');await expect(popup.getByRole('button',{name:'Start local runner',exact:true})).toBeVisible({timeout:30000});
  await popup.getByRole('button',{name:'Start local runner',exact:true}).click();
  await expect(popup.getByRole('button',{name:'Cancel',exact:true})).toBeVisible();const start=Date.now();await popup.getByRole('button',{name:'Cancel',exact:true}).click();
  await expect(popup).toHaveCount(0,{timeout:30000});
  const status=await(await page.request.get(base+'/api/v1/laomedo/runner-service')).json();if(status.reason!=='runner_start_cancelled'&&status.startup_cancelled!==true)throw Error('cancel_not_confirmed_'+status.state+'_'+status.reason);const listening=await new Promise(resolve=>{const socket=require('net').connect({host:'127.0.0.1',port:18815});socket.once('connect',()=>{socket.destroy();resolve(true)});socket.once('error',error=>{socket.destroy();resolve(error.code==='ECONNREFUSED'?false:'unknown')});socket.setTimeout(1500,()=>{socket.destroy();resolve('unknown')})});if(listening!==false)throw Error('backend_listener_not_confirmed_absent');
  await page.screenshot({path:path.join(e,'startup-cancelled-final.png')});
  const result={source_head:'02c2c291',graph:url,state:status.state,reason:status.reason,cancellation_ms:Date.now()-start,actual_ui_cancel_stopped_backend_startup:true,backend_listener_absent:true,startup_cancelled:status.startup_cancelled===true||status.reason==='runner_start_cancelled',no_model_run:before===fs.readdirSync(path.join(state,'codex/runs')).length};
  fs.writeFileSync(path.join(e,'startup-cancellation-final.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
 }finally{await browser.close()}
})().catch(error=>{console.error(error.message);process.exitCode=1});
