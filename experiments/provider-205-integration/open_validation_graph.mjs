import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
const repo='C:/CodeWorkspace/laomedo';
const metadataFile=repo+'/.tools/review/provider-composition/develop-integration/interactive-validation.json';
const metadata=JSON.parse(fs.readFileSync(metadataFile,'utf8'));
const playwrightPath=process.env.TEMP.replaceAll('\\','/')+'/laomedo-graph-20261107/readiness/pr268-upstream/src/frontend/node_modules/playwright/index.mjs';
const {chromium}=await import(pathToFileURL(playwrightPath).href);
const browser=await chromium.launch({channel:'msedge',headless:false});
try {
 const context=await browser.newContext({viewport:{width:1500,height:1000}});
 let payload=null;
 const deadline=Date.now()+180000;
 while(Date.now()<deadline) {
  try {
   const response=await context.request.get(metadata.base+'/api/v1/auto_login',{timeout:5000});
   if(response.ok()){payload=await response.json();break;}
  } catch {}
  await new Promise(resolve=>setTimeout(resolve,1000));
 }
 if(!payload?.access_token)throw new Error('Validation application did not become ready');
 const uploaded=await context.request.post(metadata.base+'/api/v1/flows/upload/',{
  headers:{Authorization:'Bearer '+payload.access_token},
  multipart:{file:{name:'validation.json',mimeType:'application/json',buffer:fs.readFileSync(metadata.graph_file)}},timeout:60000
 });
 if(!uploaded.ok())throw new Error('Graph upload HTTP '+uploaded.status());
 const flows=await uploaded.json();
 const url=metadata.base+'/flow/'+flows[0].id;
 const page=await context.newPage();
 await page.goto(url,{waitUntil:'domcontentloaded',timeout:120000});
 await page.locator('.react-flow__node').nth(1).waitFor({state:'visible',timeout:120000});
 await page.getByText(metadata.model,{exact:true}).first().waitFor({state:'visible',timeout:60000});
 const nodes=await page.locator('.react-flow__node').count();
 if(nodes!==2)throw new Error('Expected two validation Agent nodes');
 await page.screenshot({path:repo+'/.tools/review/provider-composition/develop-integration/interactive-validation-screen.png',fullPage:true});
 fs.writeFileSync(repo+'/.tools/review/provider-composition/develop-integration/interactive-validation-public.json',JSON.stringify({url,nodes,model:metadata.model,revision:metadata.revision,opened:true,executed:false},null,2));
 console.log(JSON.stringify({url,nodes,model:metadata.model,opened:true,executed:false}));
 await new Promise(resolve=>browser.on('disconnected',resolve));
} catch(error) {
 console.error(error.message);
 await browser.close();
 process.exitCode=1;
}
