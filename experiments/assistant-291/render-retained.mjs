// Capture actual retained action cards without model calls or graph mutations.
import {createRequire} from 'node:module';
import {readFile, mkdir} from 'node:fs/promises';
const require=createRequire('C:/CodeWorkspace/laomedo/.tools/assistant-282-upstream/src/frontend/package.json');
const {chromium}=require('playwright');
const root='C:/CodeWorkspace/laomedo';
const m=JSON.parse(await readFile(root+'/.tools/assistant-291-live.json','utf8'));
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const context=await browser.newContext({viewport:{width:1041,height:895},colorScheme:'dark'});
 const page=await context.newPage();
 await page.goto(m.base+'/assistant?conversation=3112d600-3026-4921-8a62-d54f2d53db09');
 await page.getByRole('article').first().waitFor({timeout:90000});
 const dir=root+'/.tools/assistant-final-cards';await mkdir(dir,{recursive:true});
 const edit=page.getByRole('article').filter({hasText:'Change the input text to compact-input'});
 await edit.screenshot({path:dir+'/edit-expired.png'});
 const rename=page.getByRole('article').filter({hasText:'to "Rename after revocation"'});
 await rename.screenshot({path:dir+'/rename-succeeded.png'});
 const run=page.getByRole('article').filter({hasText:'with input "compact-auto-input"'});
 await run.screenshot({path:dir+'/run-succeeded.png'});
 console.log(JSON.stringify({actualRetainedCards:3,noModelPrompts:true,noGraphMutation:true}));
} finally {await browser.close();}
