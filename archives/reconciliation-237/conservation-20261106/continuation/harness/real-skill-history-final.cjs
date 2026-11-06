const fs=require('fs'),path=require('path');
const {chromium,expect}=require('C:/Users/Amadou/AppData/Local/Temp/lfui-dsby42ay/lf/src/frontend/node_modules/@playwright/test');
let browser,page;
(async()=>{
const state=JSON.parse(fs.readFileSync(path.join(__dirname,'real-skill-runtime-path.json'),'utf8')).path;
const initial=JSON.parse(fs.readFileSync(path.join(__dirname,'real-skill-initial.json'),'utf8'));
browser=await chromium.launch({channel:'msedge',headless:true});
const context=await browser.newContext({storageState:path.join(state,'browser-state.json'),viewport:{width:1440,height:960}});page=await context.newPage();
await page.goto(initial.url,{waitUntil:'domcontentloaded'});const node=page.locator('.react-flow__node[data-id="skill"]');await node.waitFor({timeout:90000});await node.click();await page.getByTestId('skill-files-button').click();
await page.getByRole('button',{name:'Compare revision: Initial import',exact:true}).click();
await expect(page.getByLabel('Revision comparison',{exact:true})).toContainText('Keep publication proposals bound to their selected PR.',{timeout:45000});
await expect(page.getByText('Computing file changes...', {exact:true})).toHaveCount(0);
await page.screenshot({path:path.join(__dirname,'real-skill-history-settled.png')});
fs.writeFileSync(path.join(__dirname,'real-skill-history-settled.json'),JSON.stringify({url:initial.url,rendered_selected_file_diff:true,initial_import_and_published_edit_visible:true,raw_diff_headers_visible:await page.getByLabel('Revision comparison',{exact:true}).getByText('diff --git',{exact:false}).count()},null,2));console.log('actual_selected_file_diff_rendered');
})().catch(async e=>{if(page)await page.screenshot({path:path.join(__dirname,'real-skill-history-settled-failure.png')}).catch(()=>{});console.error(e.message);process.exitCode=1;}).finally(async()=>{if(browser)await browser.close();});
