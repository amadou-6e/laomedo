// Supporting browser regression: real app/child with one pass-through read held.
// Controlled interception is not live-workflow or owner acceptance.
const {chromium,expect}=require('@playwright/test');
const crypto=require('crypto');
const sha=value=>crypto.createHash('sha256').update(value).digest('hex');

async function main(){
 const [url,nodeId]=process.argv.slice(2),target=new URL(url);
 if(target.protocol!=='http:'||target.hostname!=='127.0.0.1'||!/^\/flow\/[0-9a-f-]+$/.test(target.pathname)||!/^[A-Za-z0-9_-]+$/.test(nodeId||''))throw Error('explicit_owned_loopback_flow_and_skill_node_required');
 let browser,context,release;const pending=[],cleanupErrors=[],writes=[];let held=false,armed=false;
 const result={scope:'Controlled pass-through browser regression only; no model, fixtures or acceptance claim',status:'running'};
 try{
  browser=await chromium.launch({channel:'msedge',headless:true});
  context=await browser.newContext({viewport:{width:1440,height:1000}});
  const page=await context.newPage();page.setDefaultTimeout(30000);
  page.on('request',request=>{const path=new URL(request.url()).pathname;if(['POST','PATCH','PUT','DELETE'].includes(request.method())&&(/\/flows\//.test(path)||/\/(build|run|runs|workflows)(\/|$)/.test(path)))writes.push({method:request.method(),path});});
  await page.goto(url,{waitUntil:'domcontentloaded'});
  const node=page.locator('.react-flow__node[data-id="'+nodeId+'"]');
  await node.getByText('Laomedo Skill',{exact:true}).click();
  await page.getByTestId('skill-files-button').click();
  const dialog=page.getByRole('dialog'),source=page.locator('.monaco-editor .view-lines');
  await expect(source).toBeVisible({timeout:30000});
  const dialogElement=await dialog.elementHandle(),sourceElement=await source.elementHandle();
  const before=sha(await source.innerText());
  const gate=new Promise(resolve=>{release=resolve});
  await page.route('**/api/v1/monitor/builds*',route=>{
   if(!armed||route.request().method()!=='GET')return route.continue();
   armed=false;held=true;
   const work=(async()=>{const response=await route.fetch();await gate;await route.fulfill({response});})();
   pending.push(work);return work;
  });
  armed=true;const started=Date.now();
  await context.setOffline(true);await context.setOffline(false);
  await expect.poll(()=>held,{timeout:10000}).toBe(true);
  await expect(dialog).toBeVisible();
  expect(await dialogElement.evaluate(element=>element.isConnected)).toBe(true);
  expect(await sourceElement.evaluate(element=>element.isConnected)).toBe(true);
  expect(sha(await source.innerText())).toBe(before);
  result.same_child_while_background_read_pending=true;
  release();await Promise.all(pending);
  await expect(dialog).toBeVisible();
  expect(await dialogElement.evaluate(element=>element.isConnected)).toBe(true);
  expect(await sourceElement.evaluate(element=>element.isConnected)).toBe(true);
  expect(sha(await source.innerText())).toBe(before);
  expect(writes).toEqual([]);
  result.same_child_after_background_read=true;result.elapsed_ms=Date.now()-started;
  result.status='supporting_browser_regression_passed_real_campaign_still_required';
 }catch(error){result.status='failed';result.failure_category=error.name;result.failure_sites=String(error.stack||'').match(/canvas_refresh\.cjs:\d+:\d+/g)||[];process.exitCode=1;}
 finally{
  release?.();
  const settled=await Promise.allSettled(pending);for(const row of settled)if(row.status==='rejected')cleanupErrors.push('pass_through_read_settlement_failed');
  if(context)await context.close().catch(()=>cleanupErrors.push('context_close_failed'));
  if(browser)await browser.close().catch(()=>cleanupErrors.push('browser_close_failed'));
  result.cleanup_errors=cleanupErrors;if(cleanupErrors.length)process.exitCode=1;
  console.log(JSON.stringify(result));
 }
}
main().catch(error=>{console.error(JSON.stringify({status:'harness_refused',category:error.name}));process.exitCode=1});
