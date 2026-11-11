// Fresh maintained PR component only. Creates a QA flow; never builds/runs nodes.
const fs = require('fs'); const path = require('path');
const runtime = path.join(process.env.TEMP, 'laomedo-graph-20261107');
const { chromium } = require(path.join(runtime, 'upstream-langflow/src/frontend/node_modules/@playwright/test'));
(async () => {
 const browser = await chromium.launch({channel:'msedge',headless:true});
 try {
  const page = await browser.newPage({viewport:{width:1600,height:1100}});
  await page.goto('http://127.0.0.1:7861/');
  await page.waitForTimeout(2500);
  const flow = JSON.parse(fs.readFileSync(path.join(__dirname,'fresh-flow.json'),'utf8'));
  flow.id = require('crypto').randomUUID(); flow.name += ' ' + Date.now();
  const created = await page.evaluate(async flow => {
   const response = await fetch('/api/v1/flows/', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(flow)});
   const body = await response.json(); return {status:response.status,id:body.id};
  }, flow);
  if (!created.id || ![200,201].includes(created.status)) throw new Error('QA flow creation refused: '+created.status);
  fs.writeFileSync(path.join(process.cwd(),'.tools/pr-readiness/268-fresh-flow-id.json'),JSON.stringify(created));
  await page.goto('http://127.0.0.1:7861/flow/'+created.id);
  const pr=page.locator('.react-flow__node[data-id="pr"]'); await pr.waitFor({timeout:60000});
  await page.waitForTimeout(4000);
  await page.waitForTimeout(350); await page.screenshot({path:'.tools/pr-readiness/268-final-fresh.png',fullPage:true});
  console.log(JSON.stringify({phase:'fresh-source',id:created.id,updateBanner:await pr.getByText('Update ready',{exact:true}).count(),comboboxes:await pr.getByRole('combobox').count()}));
  await pr.getByRole('combobox').first().click();
  await page.waitForTimeout(350); await page.screenshot({path:'.tools/pr-readiness/268-final-states.png',fullPage:true});
  console.log(JSON.stringify({phase:'states',options:await page.getByRole('option').allTextContents()}));
  await page.mouse.click(1450,400); await page.waitForTimeout(300);
  console.log(JSON.stringify({phase:'fields',fields:await pr.locator('input,textarea').evaluateAll(es=>es.map(e=>({tag:e.tagName,type:e.type,role:e.getAttribute('role'),value:e.value?.startsWith('https://github.com/')?e.value:'<not-url>'}))),combos:await pr.getByRole('combobox').allTextContents()}));
  const repository=pr.locator('input').first();
  await repository.fill('https://github.com/amadou-6e/laomedo/');
  await repository.press('Tab');
  await page.waitForTimeout(5000);
  await pr.getByText('Select labels',{exact:true}).click();
  await page.waitForTimeout(350); await page.screenshot({path:'.tools/pr-readiness/268-final-label-options.png',fullPage:true});
  console.log(JSON.stringify({phase:'label-options',options:await page.getByRole('option').allTextContents()}));
  const bug=page.getByRole('option',{name:'bug',exact:true});
  if(await bug.count()) { await bug.click(); await page.keyboard.press('Escape'); await page.waitForTimeout(2500); await pr.getByRole('combobox').filter({hasText:'bug'}).click(); await page.waitForTimeout(350); await page.screenshot({path:'.tools/pr-readiness/268-final-label-selected.png',fullPage:true}); await page.getByRole('option',{name:'bug',exact:true}).click(); await page.mouse.click(1450,400); await pr.getByText('Select labels',{exact:true}).waitFor({timeout:15000}); await page.waitForTimeout(1500); await page.screenshot({path:'.tools/pr-readiness/268-final-label-cleared.png',fullPage:true}); console.log(JSON.stringify({phase:'label-cleared',bugRemoved:true})); }
  else await page.keyboard.press('Escape');
  await repository.fill('https://github.com/amadou-6e/unconfigured-selector-qa-20261111');
  await repository.press('Tab'); await page.waitForTimeout(3500);
  await page.waitForTimeout(350); await page.screenshot({path:'.tools/pr-readiness/268-final-connection-refused.png',fullPage:true});
  console.log(JSON.stringify({phase:'connection-refused',text:await pr.innerText()}));
  await repository.fill('https://github.com/amadou-6e/laomedo');
  await repository.press('Tab'); await page.waitForTimeout(4000);
  await pr.getByText('Select a PR',{exact:true}).click();
  const search=page.getByTestId('dropdown_search_input');
  await search.fill('recovry');
  await page.getByText('#264 Fix managed Codex recovery in native app startup',{exact:true}).waitFor({timeout:15000});
  await page.waitForTimeout(350); await page.screenshot({path:'.tools/pr-readiness/268-final-search.png',fullPage:true});
  await search.fill('no-match-final-qa-20261111'); await page.waitForTimeout(300);
  await page.waitForTimeout(350); await page.screenshot({path:'.tools/pr-readiness/268-final-no-match.png',fullPage:true});
  console.log(JSON.stringify({phase:'fresh-fuzzy-and-no-match',matched264:true,updateBanner:await pr.getByText('Update ready',{exact:true}).count()}));
  await search.fill('264');
  await page.getByText('#264 Fix managed Codex recovery in native app startup',{exact:true}).click();
  await pr.getByText('GitHub PR',{exact:true}).click(); await page.waitForTimeout(500);
  await pr.getByText('PR viewer',{exact:true}).click();
  const loading=page.getByText('Loading current PR...',{exact:true});
  if(await loading.count()) { await page.screenshot({path:'.tools/pr-readiness/268-final-viewer-loading.png',fullPage:true}); }
  await page.getByTestId('pr-viewer-content').waitFor({timeout:60000});
  await page.screenshot({path:'.tools/pr-readiness/268-final-viewer.png',fullPage:true});
  console.log(JSON.stringify({phase:'real-pr-inspection',number:264,externalHref:await page.getByTestId('pr-open-browser').getAttribute('href'),noAgentTask:true}));



 } finally { await browser.close(); }
})().catch(e=>{console.error(e.message);process.exit(1)});
