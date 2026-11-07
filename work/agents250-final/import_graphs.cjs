const fs=require('fs'),path=require('path');
const {chromium}=require('C:/Users/Amadou/AppData/Local/Temp/lfui-dsby42ay/lf/src/frontend/node_modules/@playwright/test');
(async()=>{
 const e='C:/CodeWorkspace/laomedo/claude-review.local/agents-250-20261107';
 const state=JSON.parse(fs.readFileSync(path.join(e,'runtime-path.json'))).path;
 const browser=await chromium.launch({channel:'msedge',headless:true});
 try {
  const context=await browser.newContext({viewport:{width:1600,height:1100}}),page=await context.newPage();
  await page.goto('http://127.0.0.1:17863');
  await page.getByRole('button').first().waitFor({timeout:90000});
  const graphs=[];
  for(const provider of ['codex','claude','opencode']) {
   const flow=JSON.parse(fs.readFileSync(path.join(state,provider+'-flow.json')));
   const response=await page.request.post('http://127.0.0.1:17863/api/v1/flows/',{data:flow});
   if(!response.ok())throw Error('import_'+provider+'_'+response.status());
   const saved=await response.json(),url='http://127.0.0.1:17863/flow/'+saved.id;
   await page.goto(url);
   const node=page.locator('.react-flow__node[data-id="agent"]');
   await node.waitFor({timeout:90000});
   await page.screenshot({path:path.join(e,provider+'-before.png')});
   const controls=await node.locator('input,textarea,[role="combobox"],button').evaluateAll(es=>es.map(el=>({tag:el.tagName,role:el.getAttribute('role'),testid:el.getAttribute('data-testid'),aria:el.getAttribute('aria-label'),text:el.textContent?.slice(0,100),value:el.value})));
   graphs.push({provider,id:saved.id,url,controls});
  }
  await context.storageState({path:path.join(state,'browser-state.json')});
  fs.writeFileSync(path.join(e,'live-graphs.json'),JSON.stringify(graphs,null,2));
  console.log(JSON.stringify(graphs));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
