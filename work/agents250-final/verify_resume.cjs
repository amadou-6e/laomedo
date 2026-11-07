const fs=require('fs'),path=require('path');
const {chromium,expect}=require('C:/Users/Amadou/AppData/Local/Temp/lfui-dsby42ay/lf/src/frontend/node_modules/@playwright/test');
(async()=>{const e='C:/CodeWorkspace/laomedo/claude-review.local/agents-250-20261107',state=JSON.parse(fs.readFileSync(path.join(e,'runtime-path.json'))).path;
 const observations=JSON.parse(fs.readFileSync(path.join(e,'resume-first-observations.json'))),latestClaude=path.join(e,'claude-resume-result.json');
 if(fs.existsSync(latestClaude)){const latest=JSON.parse(fs.readFileSync(latestClaude));observations[observations.findIndex(r=>r.provider==='claude')]=latest;}
 const b=await chromium.launch({channel:'msedge',headless:true}),results=[];
 try{const c=await b.newContext({viewport:{width:1600,height:1100},storageState:path.join(state,'browser-state.json')}),p=await c.newPage();
 for(const old of observations){const r=JSON.parse(fs.readFileSync(path.join(state,old.provider,'runs',old.run_id,'record.json')));
  if(r.status!=='completed'||r.turns.length!==2||r.activity_attempt_id===r.activity_initial_attempt_id||!r.attempt_finished)throw Error('resume_not_final_'+old.provider+'_'+r.status);
  await p.goto(old.graph);await p.locator('.react-flow__node[data-id="follow-up"]').waitFor({timeout:90000});
  await expect(p.locator('.react-flow__edge')).toHaveCount(1);await expect(p.locator('.react-flow__node[data-id="follow-up"]').getByText('Prior Run',{exact:true})).toBeVisible();
  await p.reload();await expect(p.locator('.react-flow__edge')).toHaveCount(1,{timeout:90000});
  await p.screenshot({path:path.join(e,old.provider+'-resume-final-graph.png')});
  await p.getByTestId('sidebar-nav-agents').click();await expect(p.getByTestId('agent-timeline-row')).toHaveCount(2,{timeout:30000});
  await p.getByTestId('agent-timeline-row').last().getByRole('button').first().click();await expect(p.getByRole('article',{name:'Selected agent run'})).toBeVisible();
  await expect(p.getByRole('region',{name:'Graph agent activity'})).toContainText(/Contributing|Getting started|getting-started|CONTRIBUTING|pip install/,{timeout:10000});
  await p.screenshot({path:path.join(e,old.provider+'-resume-final-activity.png')});
  const firstNative=old.provider==='claude'?r.turns[0].native_session_id:old.first_native_session;
  const sameNative=firstNative===r.thread_id&&(old.provider!=='claude'||r.turns.every(t=>t.native_session_id===firstNative));
  if(!sameNative)throw Error('native_session_changed_'+old.provider);
  const value={provider:old.provider,graph:old.graph,run_id:r.run_id,status:r.status,first_native_session:firstNative,final_native_session:r.thread_id,same_native_session:sameNative,turn_count:r.turns.length,distinct_activity_attempts:r.activity_attempt_id!==r.activity_initial_attempt_id,first_activity_attempt:r.activity_initial_attempt_id,final_activity_attempt:r.activity_attempt_id,answer:r.answer,controller_cleanup:r.controller_cleanup,descendant_cleanup:r.descendant_cleanup,edge_survives_import_and_reload:true,connected_port_visible:true,activity_rows:2};
  results.push(value);console.log(JSON.stringify(value));fs.writeFileSync(path.join(e,'resume-final-results.json'),JSON.stringify(results,null,2));
 }
 }finally{await b.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
