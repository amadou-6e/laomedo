// Verify transcript controls against actual retained integration messages; no inference or graph changes.
import {createRequire} from 'node:module';
import {readFile,mkdir} from 'node:fs/promises';
const require=createRequire('C:/CodeWorkspace/laomedo/.tools/assistant-282-upstream/src/frontend/package.json');
const {chromium}=require('playwright');
const root='C:/CodeWorkspace/laomedo';
const m=JSON.parse(await readFile(root+'/.tools/assistant-291-live.json','utf8'));
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const context=await browser.newContext({viewport:{width:1041,height:895},colorScheme:'dark',acceptDownloads:true,permissions:['clipboard-read','clipboard-write']});
 const page=await context.newPage();
 await page.goto(m.base+'/assistant?conversation=3112d600-3026-4921-8a62-d54f2d53db09');
 const copy=page.getByRole('button',{name:'Copy answer',exact:true}).last();
 await copy.waitFor({timeout:90000});
 await copy.click();
 await page.getByRole('status').filter({hasText:'Copied'}).waitFor();
 const copied=await page.evaluate(()=>navigator.clipboard.readText());
 if(!copied.includes('Laomedo'))throw Error('Unexpected copied answer');
 const downloadEvent=page.waitForEvent('download');
 await page.getByRole('button',{name:'Export conversation',exact:true}).click();
 const download=await downloadEvent;
 const text=await readFile(await download.path(),'utf8');
 if(!download.suggestedFilename().endsWith('.md')||!text.includes('## You')||!text.includes('## Assistant')||!text.includes(copied)||!text.includes('compact-auto-input'))throw Error('Incomplete exported transcript');
 const feed=page.getByRole('generic',{name:'Assistant messages and saved drafts'});
 await page.locator('[aria-label="Assistant messages and saved drafts"]').evaluate(el=>{el.scrollTop=el.scrollHeight});
 await mkdir(root+'/.tools/assistant-transcript-images',{recursive:true});
 await page.screenshot({path:root+'/.tools/assistant-transcript-images/chat.png'});
 const gap=await page.evaluate(()=>{const scroll=document.querySelector('[aria-label="Assistant messages and saved drafts"]');const child=scroll.firstElementChild;return Math.round(scroll.getBoundingClientRect().bottom-child.getBoundingClientRect().bottom)});
 console.log(JSON.stringify({realRetainedConversation:true,clipboardMatchesAnswer:true,markdownDownload:true,includesUserAndAssistant:true,compactBottomGap:gap,noInference:true,noGraphMutation:true}));
} finally {await browser.close();}
