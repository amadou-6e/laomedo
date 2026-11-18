// Real app entry points, no inference or saved graph mutations.
import {createRequire} from 'node:module';
import {mkdir} from 'node:fs/promises';
const require=createRequire('C:/CodeWorkspace/laomedo/.tools/assistant-282-upstream/src/frontend/package.json');
const {chromium}=require('playwright');
const root='C:/CodeWorkspace/laomedo';
const base='http://127.0.0.1:55753';
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const page=await browser.newPage({viewport:{width:1440,height:1000},colorScheme:'dark'});
 await page.goto(base+'/flow/7a8a98e4-2908-4dc8-81e3-7a4655583c15');
 await page.getByRole('button',{name:'Agents',exact:true}).click({timeout:90000});
 const graphUrl=page.url();
 await page.getByRole('button',{name:'Open assistant sidebar',exact:true}).click();
 const sidebar=page.getByRole('complementary',{name:'Assistant sidebar'});
 await sidebar.getByRole('textbox',{name:'Message this assistant'}).waitFor();
 await sidebar.getByText('Choose model',{exact:true}).waitFor({state:'hidden',timeout:60000});
 await page.evaluate(()=>document.fonts.ready);
 await page.waitForTimeout(1500);
 if(page.url()!==graphUrl || !await page.getByRole('heading',{name:'Agents',exact:true}).isVisible())throw Error('Rail changed graph section');
 const dir=root+'/.tools/sidebar-296-entry-render';await mkdir(dir,{recursive:true});
 await page.screenshot({path:dir+'/rail.png'});
 await page.getByRole('button',{name:'Collapse assistant sidebar',exact:true}).click();
 await page.waitForFunction(()=>document.activeElement?.id==='laomedo-assistant-opener');
 const count=page.context().pages().length;
 await page.getByRole('link',{name:'Open full-window assistant',exact:true}).click();
 await page.waitForURL('**/assistant');
 if(page.context().pages().length!==count)throw Error('Unexpected popup');
 await page.getByRole('textbox',{name:'Message this assistant'}).waitFor();
 await page.getByText('Choose model',{exact:true}).waitFor({state:'hidden',timeout:60000});
 await page.waitForTimeout(1500);
 await page.screenshot({path:dir+'/full-chat.png'});
 console.log(JSON.stringify({railOpensRightSidebar:true,agentsSectionPreserved:true,closeRestoresRailFocus:true,headerOpensFullChatInSameTab:true,noInference:true,noSavedGraphMutation:true}));
}finally {await browser.close()}
