const fs=require('fs'),path=require('path');
const {chromium}=require('C:/Users/Amadou/AppData/Local/Temp/lfui-dsby42ay/lf/src/frontend/node_modules/@playwright/test');
(async()=>{
 const e='C:/CodeWorkspace/laomedo/claude-review.local/agents-250-20261107',state=JSON.parse(fs.readFileSync(path.join(e,'runtime-path.json'))).path;
 const browser=await chromium.launch({channel:'msedge',headless:true}),results=[],graphs=[];
 try{
  const context=await browser.newContext({viewport:{width:1600,height:1100},storageState:path.join(state,'browser-state.json')}),page=await context.newPage();
  await page.goto('http://127.0.0.1:17863');await page.getByRole('button').first().waitFor({timeout:90000});
  for(const provider of (process.argv[2]?[process.argv[2]]:['codex','claude','opencode'])){
   const flow=JSON.parse(fs.readFileSync(path.join(state,provider+'-resume-flow.json')));
   const savedResponse=await page.request.post('http://127.0.0.1:17863/api/v1/flows/',{data:flow});
   if(!savedResponse.ok())throw Error('resume_import_'+savedResponse.status());
   const saved=await savedResponse.json(),url='http://127.0.0.1:17863/flow/'+saved.id;
   graphs.push({provider,id:saved.id,url});fs.writeFileSync(path.join(e,'resume-graphs.json'),JSON.stringify(graphs,null,2));
   await page.goto(url);const node=page.locator('.react-flow__node[data-id="follow-up"]');await node.waitFor({timeout:90000});
   const dir=path.join(state,provider,'runs'),before=new Set(fs.readdirSync(dir)),started=Date.now();
   await node.getByRole('button',{name:'Run component',exact:true}).click();
   let record,firstThread,firstAttempt,firstAnswer;const deadline=Date.now()+300000;
   while(Date.now()<deadline){
    const added=fs.readdirSync(dir).filter(n=>!before.has(n));if(added.length>1)throw Error('resume_created_second_run_'+provider);
    if(added.length){try{record=JSON.parse(fs.readFileSync(path.join(dir,added[0],'record.json')))}catch{}
     if(record?.thread_id&&!firstThread){firstThread=record.thread_id;firstAttempt=record.activity_initial_attempt_id;}
     if(record?.attempt_number===1&&record.status==='completed')firstAnswer=record.answer;
     if(record?.turns?.length>=2&&record.activity_attempt_id!==record.activity_initial_attempt_id&&['completed','failed','cancelled','interrupted','timed_out','unknown'].includes(record.status)&&record.attempt_finished)break;
     if(record?.status==='failed')break;
    }
    if(await page.getByText('Flow build failed',{exact:true}).count()||await page.getByText('No previous run is available',{exact:true}).count())break;
    if(!record&&Date.now()-started>45000)break;
    await page.waitForTimeout(500);
   }
   await page.screenshot({path:path.join(e,provider+'-resume.png')});
   const value={provider,graph:url,status:record?.status||'not_submitted',run_id:record?.run_id,attempt_number:record?.attempt_number,first_native_session:firstThread,final_native_session:record?.thread_id,same_native_session:!!firstThread&&firstThread===record?.thread_id,first_activity_attempt:firstAttempt,final_activity_attempt:record?.activity_attempt_id,first_answer:firstAnswer,answer:record?.answer,turn_count:record?.turns?.length,error_category:record?.error_category,controller_cleanup:record?.controller_cleanup,descendant_cleanup:record?.descendant_cleanup,elapsed_ms:Date.now()-started,visible_failure:!!await page.getByText('Flow build failed',{exact:true}).count()};
   results.push(value);fs.writeFileSync(path.join(e,provider+'-resume-result.json'),JSON.stringify(value,null,2));fs.writeFileSync(path.join(e,'resume-browser-results.json'),JSON.stringify(results,null,2));console.log(JSON.stringify(value));
  }
 }finally{await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
