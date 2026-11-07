const fs=require('fs'),path=require('path');
const {chromium,expect}=require('C:/Users/Amadou/AppData/Local/Temp/lfui-dsby42ay/lf/src/frontend/node_modules/@playwright/test');
(async()=>{
 const e='C:/CodeWorkspace/laomedo/claude-review.local/agents-250-20261107',state=JSON.parse(fs.readFileSync(path.join(e,'runtime-path.json'))).path;
 const graphs=JSON.parse(fs.readFileSync(path.join(e,'live-graphs.json'))),results=[];
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  const context=await browser.newContext({viewport:{width:1600,height:1100},storageState:path.join(state,'browser-state.json')}),page=await context.newPage();
  await page.goto('http://127.0.0.1:17863');await page.getByRole('button').first().waitFor({timeout:90000});
  for(const graph of graphs) {
   const dir=path.join(state,graph.provider,'runs'),before=new Set(fs.existsSync(dir)?fs.readdirSync(dir):[]),errors=[];
   const onError=error=>errors.push(error.message);page.on('pageerror',onError);
   await page.goto(graph.url);
   const node=page.locator('.react-flow__node[data-id="agent"]');await node.waitFor({timeout:90000});
   const started=Date.now();await node.getByRole('button',{name:'Run component',exact:true}).click();
   let record,file;const deadline=Date.now()+260000;
   while(Date.now()<deadline) {
    const added=(fs.existsSync(dir)?fs.readdirSync(dir):[]).filter(n=>!before.has(n));
    if(added.length>1)throw Error('unexpected_duplicate_native_run_'+graph.provider);
    if(added.length){file=path.join(dir,added[0],'record.json');if(fs.existsSync(file)){try{record=JSON.parse(fs.readFileSync(file))}catch{};if(record&&['completed','failed','cancelled','interrupted','timed_out'].includes(record.status))break;}}
    // Fail early on real graph errors that prevented provider admission.
    if(!record&&await page.getByText('Flow build failed',{exact:true}).count())break;
    await page.waitForTimeout(750);
   }
   await page.screenshot({path:path.join(e,graph.provider+'-after.png')});
   const body=await page.locator('body').innerText();
   const result={provider:graph.provider,graph:graph.url,elapsed_ms:Date.now()-started,
    run_id:record?.run_id,status:record?.status||'not_submitted',error_category:record?.error_category,
    thread_id:record?.thread_id,answer:record?.answer,new_native_runs:(fs.existsSync(dir)?fs.readdirSync(dir):[]).filter(n=>!before.has(n)).length,
    cleanup_verified:record?.cleanup_verified,termination_verified:record?.termination_verified,
    page_errors:errors,visible_failure:body.includes('Flow build failed'),record_keys:record?Object.keys(record):[]};
   fs.writeFileSync(path.join(e,graph.provider+'-live-run.json'),JSON.stringify(result,null,2));
   if(file)fs.writeFileSync(path.join(state,graph.provider+'-record-path.json'),JSON.stringify({path:file}));
   results.push(result);console.log(JSON.stringify(result));page.off('pageerror',onError);
  }
  fs.writeFileSync(path.join(e,'live-runs.json'),JSON.stringify(results,null,2));
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
