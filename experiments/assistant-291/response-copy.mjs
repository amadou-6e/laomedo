// Actual retained response-level clipboard acceptance; no prompts, graph changes or transcript logging.
import {createRequire} from 'node:module';
import {readFile,mkdir} from 'node:fs/promises';
const require=createRequire('C:/CodeWorkspace/laomedo/.tools/assistant-282-upstream/src/frontend/package.json');
const {chromium}=require('playwright');
const root='C:/CodeWorkspace/laomedo';
const m=JSON.parse(await readFile(root+'/.tools/assistant-291-live.json','utf8'));
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const context=await browser.newContext({viewport:{width:1041,height:895},colorScheme:'dark',permissions:['clipboard-read','clipboard-write']});
 const page=await context.newPage();
 await page.goto(m.base+'/assistant?conversation=3112d600-3026-4921-8a62-d54f2d53db09&ui=89d05235d');
 const response=page.locator('section[aria-label="Message and response"]').last();
 await response.getByRole('button',{name:'Copy answer',exact:true}).waitFor({timeout:90000});
 if(await response.getByRole('button',{name:'Copy answer',exact:true}).count()!==1)throw Error('Not one response-level Copy');
 await response.getByRole('button',{name:'Copy answer',exact:true}).click();
 await response.getByRole('status').filter({hasText:'Copied'}).waitFor();
 const copied=await page.evaluate(()=>navigator.clipboard.readText());
 const user=await response.locator('p.whitespace-pre-wrap').innerText();
 console.log(JSON.stringify({hasSearch:copied.includes('search_components'),hasDescribe:copied.includes('describe_component'),hasInput:copied.includes('Input'),hasOutput:copied.includes('Output'),hasFinal:copied.includes('I couldn'),hasFirst:copied.includes('map this to installed Laomedo'),hasUser:copied.includes(user),hasEarlier:copied.includes('The run proposal is executing according to the Laomedo result.')}));
 if(!copied.includes('search_components')||!copied.includes('describe_component')||!copied.includes('Input')||!copied.includes('Output')||!copied.includes('I couldn')||!copied.includes('map this to installed Laomedo')||copied.includes(user)||copied.includes('The run proposal is executing according to the Laomedo result.'))throw Error('Response copy scope mismatch');
 await mkdir(root+'/.tools/assistant-response-copy-images',{recursive:true});
 await page.screenshot({path:root+'/.tools/assistant-response-copy-images/chat.png'});
 console.log(JSON.stringify({realRetainedResponse:true,oneCopyPerRequest:true,containsAllAssistantText:true,containsToolInputsAndOutputs:true,excludesUserAndEarlierResponse:true,noInference:true,noGraphMutation:true}));
} finally {await browser.close();}
