const path=require('path');
const runtime=path.join(process.env.TEMP,'laomedo-graph-20261107');
const {chromium}=require(path.join(runtime,'upstream-langflow/src/frontend/node_modules/@playwright/test'));
(async()=>{const browser=await chromium.launch({channel:'msedge',headless:true});try{
const page=await browser.newPage(); await page.goto('http://127.0.0.1:7860/flow/b0c4e79b-b678-4a25-8f84-2cacf155efa4'); await page.locator('.react-flow__node[data-id="pr"]').waitFor();
const endpoint='http://127.0.0.1:7860/api/v1/laomedo/runner-service';
let r=await page.request.get(endpoint); let s=await r.json();console.log(JSON.stringify({phase:'before',http:r.status(),state:s.state,reason:s.reason,can_start:s.can_start}));
if(s.can_start){r=await page.request.post(endpoint+'/start');s=await r.json();console.log(JSON.stringify({phase:'start',http:r.status(),state:s.state,reason:s.reason}));}
for(let i=0;i<45&&s.state==='starting';i++){await page.waitForTimeout(1000);r=await page.request.get(endpoint);s=await r.json();}
console.log(JSON.stringify({phase:'after',http:r.status(),state:s.state,reason:s.reason}));
}finally{await browser.close();}})().catch(e=>{console.error(e.message);process.exit(1)});
