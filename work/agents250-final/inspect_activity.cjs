const fs=require('fs'),path=require('path');
const {chromium,expect}=require('C:/Users/Amadou/AppData/Local/Temp/lfui-dsby42ay/lf/src/frontend/node_modules/@playwright/test');
(async()=>{
 const e='C:/CodeWorkspace/laomedo/claude-review.local/agents-250-20261107',state=JSON.parse(fs.readFileSync(path.join(e,'runtime-path.json'))).path;
 const graphs=JSON.parse(fs.readFileSync(path.join(e,'live-graphs.json'))),browser=await chromium.launch({channel:'msedge',headless:true});
 try{
 const context=await browser.newContext({viewport:{width:1600,height:1100},storageState:path.join(state,'browser-state.json')}),page=await context.newPage();
 await page.goto(graphs[0].url);await page.locator('.react-flow__node').waitFor({timeout:90000});await page.waitForTimeout(1800);
 console.log(JSON.stringify(await page.getByRole('button').evaluateAll(es=>es.filter(e=>e.getAttribute('data-sidebar')||e.getAttribute('aria-label')||e.getAttribute('title')).map(e=>({text:e.innerText,aria:e.getAttribute('aria-label'),title:e.getAttribute('title'),testid:e.getAttribute('data-testid'),sidebar:e.getAttribute('data-sidebar')})))));
 await page.screenshot({path:path.join(e,'codex-graph-terminal.png')});
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
