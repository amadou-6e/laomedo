const fs=require('fs'),path=require('path');
const {chromium,expect}=require('C:/Users/Amadou/AppData/Local/Temp/lfui-dsby42ay/lf/src/frontend/node_modules/@playwright/test');
(async()=>{
 const e='C:/CodeWorkspace/laomedo/claude-review.local/agents-250-20261107';
 const state=path.join(JSON.parse(fs.readFileSync(path.join(e,'runtime-path.json'))).path,'recovery-preview');
 const base='http://127.0.0.1:17864',browser=await chromium.launch({channel:'msedge',headless:true});
 let page;const polls=[],pending=[];const observedStart=Date.now();
 try{
  const context=await browser.newContext({viewport:{width:1440,height:1000},permissions:['clipboard-read','clipboard-write']});page=await context.newPage();
  page.on('response',response=>{if(new URL(response.url()).pathname==='/api/v1/laomedo/runner-service')pending.push(response.json().then(value=>polls.push({elapsed_ms:Date.now()-observedStart,state:value.state,reason:value.reason,http_status:response.status()})).catch(()=>{}));});
  await page.goto(base);await page.getByRole('button').first().waitFor({timeout:90000});
  const imported=await page.request.post(base+'/api/v1/flows/',{data:JSON.parse(fs.readFileSync(path.join(state,'flow.json')))});
  if(!imported.ok())throw Error('recovery_graph_import_'+imported.status());
  const graph=await imported.json(),url=base+'/flow/'+graph.id;await page.goto(url);
  const node=page.locator('.react-flow__node[data-id="agent"]');await node.waitFor({timeout:90000});
  const dismissOnboarding=async()=>{const button=page.getByRole('button',{name:'Dismiss assistant onboarding tooltip',exact:true});await button.waitFor({timeout:3000}).then(()=>button.click()).catch(()=>{});};
  const before=(fs.existsSync(path.join(state,'runner/runs'))?fs.readdirSync(path.join(state,'runner/runs')):[]).length;
  const serviceBefore=await (await page.request.get(base+'/api/v1/laomedo/runner-service')).json();
  if(serviceBefore.state!=='offline')throw Error('recovery_precondition_not_offline_'+serviceBefore.state);
  await node.getByRole('button',{name:'Run component',exact:true}).click();
  const popup=page.locator('[role="region"][data-error-code="runner_transport_failed"]');
  await expect(popup).toBeVisible({timeout:30000});
  await expect(popup.getByRole('button',{name:'Start local runner',exact:true})).toBeVisible({timeout:30000});
  await page.getByTestId('assistant-onboarding-tooltip').waitFor({timeout:15000});await expect(popup).toBeVisible();
  await page.getByRole('button',{name:'Parameters',exact:true}).click();
  await expect(page.getByText('Component Parameters',{exact:true})).toBeVisible();
  await expect(page.getByText('Prior Run',{exact:true})).toHaveCount(0);
  await expect(popup).toBeVisible();
  await page.getByRole('button',{name:'Parameters',exact:true}).click();
  await page.locator('.react-flow__node[data-id="modal-target"]').getByText('Laomedo Agent Handoff',{exact:true}).click();
  await page.getByTestId('code-button-modal').click();
  const modal=page.getByRole('dialog').filter({has:page.locator('#codeValue')});
  await expect(modal).toBeVisible();await expect(popup).toBeHidden();
  await page.screenshot({path:path.join(e,'recovery-isolated-real-modal.png')});
  await page.keyboard.press('Escape');await expect(modal).toHaveCount(0);await expect(popup).toBeVisible();
  await popup.getByText('Technical details',{exact:true}).click();await popup.getByRole('button',{name:'Copy diagnostics',exact:true}).click();
  const copied=JSON.parse(await page.evaluate(()=>navigator.clipboard.readText())),bounds=await popup.boundingBox();
  if(!bounds||bounds.x<0||bounds.y<0||bounds.x+bounds.width>1440||bounds.y+bounds.height>1000)throw Error('popup_outside_viewport');
  await page.screenshot({path:path.join(e,'recovery-isolated-offline.png')});
  await popup.getByRole('button',{name:'Start local runner',exact:true}).click();
  await expect(popup.getByRole('button',{name:'Cancel',exact:true})).toBeVisible();await expect(popup.locator('[aria-busy="true"]')).toBeVisible();
  await page.screenshot({path:path.join(e,'recovery-isolated-starting.png')});
  await expect(popup).toContainText('The local runner is online.',{timeout:90000});
  await expect.poll(async()=>{
   const messages=await page.locator('[aria-label="Local backend recovery"] [role="status"]').allTextContents();
   return messages.length>=2&&messages.every(text=>text.includes('The local runner is online.'));
  },{timeout:20000}).toBe(true);
  const service=await (await page.request.get(base+'/api/v1/laomedo/runner-service')).json(),border=await popup.evaluate(el=>getComputedStyle(el).borderLeftColor);
  await page.screenshot({path:path.join(e,'recovery-isolated-online.png')});
  const after=fs.readdirSync(path.join(state,'runner/runs')).length;
  await popup.getByRole('button',{name:'Dismiss',exact:true}).click();await expect(popup).toHaveCount(0);
  const result={graph:url,source_binding:{frontend_source_revision:'4b81988b6d554a618ea18ea3da9a05f994ed21ce',parity_record:'deployment-parity-final.json'},offline_error_code:copied.code,copy_icon_works:copied.code==='runner_transport_failed',viewport_bounds:bounds,busy_spinner_and_cancel_button:true,visible_with_actual_nonmodal_onboarding:true,actual_modal_hides_background_and_close_restores_it:true,service_state:service.state,online_border_color:border,online_border_green:border==='rgb(74, 222, 128)',no_graph_rerun_or_native_submission:before===after,dismissed:true,startup_cancellation:'not exercised in this pass'};
  fs.writeFileSync(path.join(e,'recovery-isolated-result.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result));
  await Promise.allSettled(pending);fs.writeFileSync(path.join(e,'recovery-poll-observations.json'),JSON.stringify(polls,null,2));
 }catch(error){if(page){await page.screenshot({path:path.join(e,'recovery-isolated-failure.png')}).catch(()=>{});console.error((await page.locator('body').innerText()).slice(-2200));}throw error;}
 finally{await browser.close()}
})().catch(e=>{console.error(e.message);process.exitCode=1});
