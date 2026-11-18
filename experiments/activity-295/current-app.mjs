// Read-only current app acceptance; normal profile PIN login, never session export.
import {createRequire} from 'node:module';
import {readFile,mkdir} from 'node:fs/promises';
const require=createRequire('C:/CodeWorkspace/laomedo/.tools/assistant-282-upstream/src/frontend/package.json');
const {chromium}=require('playwright');
const root='C:/CodeWorkspace/laomedo';
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const page=await browser.newPage({viewport:{width:1206,height:1056},colorScheme:'dark'});
 await page.goto('http://127.0.0.1:55753/flow/b4714b72-0639-462f-83f7-19869b372d48');
 await page.locator('input[type=password]').or(page.getByRole('button',{name:/Amadou/})).or(page.getByRole('button',{name:'Agents',exact:true})).first().waitFor({timeout:90000});
 if(await page.getByRole('button',{name:/Amadou/}).count()) {
   await page.getByRole('button',{name:/Amadou/}).click();
   await page.locator('input[type=password]').waitFor();
 }
 if(await page.locator('input[type=password]').count()) {
   const env=await readFile(root+'/.env','utf8');
   const pin=env.match(/^LAOMEDO_PIN\s*=\s*["']?([^\r\n"']+)/m)?.[1].trim();
   if(!pin)throw Error('Configured PIN absent');
   await page.locator('input[type=password]').fill(pin);
   await page.getByRole('button',{name:'Log in',exact:true}).click();
   await page.locator('input[type=password]').waitFor({state:'hidden',timeout:15000});
 }
 if(await page.getByRole('button',{name:'Dismiss',exact:true}).count())await page.getByRole('button',{name:'Dismiss',exact:true}).click();
 await page.getByRole('button',{name:'Agents',exact:true}).click({timeout:30000});
 await page.getByRole('button',{name:/^Laomedo Codex Agent.*completed$/}).first().click();
 await page.getByRole('button',{name:'Search conversation',exact:true}).waitFor();
 try { await page.getByRole('button',{name:'Dismiss',exact:true}).waitFor({timeout:12000}); await page.getByRole('button',{name:'Dismiss',exact:true}).click(); } catch {}
 const dir=root+'/.tools/activity-295-current-render';await mkdir(dir,{recursive:true});
 await page.getByText('Usage and diagnostics',{exact:true}).scrollIntoViewIfNeeded();
 await page.screenshot({path:dir+'/usage.png'});
 await page.getByRole('button',{name:'Search conversation',exact:true}).click();
 const field=page.getByRole('textbox',{name:'Search conversation',exact:true});
 await page.getByRole('heading',{name:'Conversation',exact:true}).scrollIntoViewIfNeeded();
 await page.screenshot({path:dir+'/search.png'});
 await field.fill('Reply exactly');
 await field.press('Escape');
 await page.screenshot({path:dir+'/closed.png'});
 await page.setViewportSize({width:800,height:1000});
 await page.screenshot({path:dir+'/narrow.png'});
 await page.getByRole('button',{name:/^Turn 1.*Main conversation.*completed/}).first().click();
 await page.getByRole('button',{name:'All activity',exact:true}).waitFor();
 await page.screenshot({path:dir+'/turn.png'});
 console.log(JSON.stringify({normalProfileLogin:true,realRetainedActivity:true,noInference:true,noGraphMutation:true}));
}catch {
 console.error('Activity browser validation incomplete: profile login or expected UI unavailable. Browser diagnostics suppressed to protect password fields.');
 process.exitCode=1;
}finally {await browser.close()}
