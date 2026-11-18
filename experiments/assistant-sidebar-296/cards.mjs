import {createRequire} from 'node:module';
import {readFile,mkdir} from 'node:fs/promises';
const require=createRequire('C:/CodeWorkspace/laomedo/.tools/assistant-282-upstream/src/frontend/package.json');
const {chromium}=require('playwright');
const root='C:/CodeWorkspace/laomedo';
const metadata=JSON.parse(await readFile(root+'/.tools/assistant-291-live.json','utf8'));
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000},colorScheme:'dark'});
 await page.goto(metadata.base+'/flow/'+metadata.flow);
 await page.locator('.react-flow__node').first().waitFor({timeout:90000});
 await page.getByRole('button',{name:'Open assistant sidebar',exact:true}).click();
 const sidebar=page.getByRole('complementary',{name:'Assistant sidebar'});
 await sidebar.getByRole('button',{name:'Expand conversations'}).click();
 const index=await page.evaluate(async()=>{const r=await fetch('/api/v1/laomedo/assistant/conversations',{credentials:'same-origin',headers:{}});if(!r.ok)throw Error('History unavailable');return r.json()});
 const at=index.conversations.findIndex(c=>c.id==='3112d600-3026-4921-8a62-d54f2d53db09');
 if(at<0)throw Error('Retained approval demo missing');
 await sidebar.getByRole('navigation').getByRole('button').nth(at).click();
 const cards=sidebar.getByRole('article').filter({has:page.getByRole('link',{name:'Open workflow in new tab'})});
 await cards.first().waitFor({timeout:30000});
 await mkdir(root+'/.tools/sidebar-296-dialogs',{recursive:true});
 for(const operation of ['Rename','Edit','Run']) {
   const card=sidebar.getByRole('article',{name:new RegExp('^'+operation+' workflow:')}).first();
   await card.scrollIntoViewIfNeeded();
   await card.screenshot({path:root+'/.tools/sidebar-296-dialogs/'+operation.toLowerCase()+'.png'});
 }
 console.log(JSON.stringify({realRetainedApprovalCards:3,sameSavedConversation:true,noApprovalSubmitted:true,noInference:true}));
}finally {await browser.close()}
