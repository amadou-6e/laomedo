const {chromium,expect}=require('@playwright/test');
const fs=require('fs'); let browser;
(async()=>{
 const f=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));expect(f.provider).toBe('fake-no-network');
 browser=await chromium.launch({channel:'msedge'});const page=await browser.newPage({viewport:{width:1400,height:1000}});
 await page.goto(f.url);const node=page.locator('.react-flow__node[data-id="issue"]');await node.waitFor({timeout:60000});await node.click();
 const status=node.getByTestId('skill-discovery-status');
 const input=node.getByTestId('popover-anchor-input-repository_url');
 await input.fill('https://github.com/owner/repo');await input.press('Tab');
 await expect(status).toHaveText('2 matching issues.',{timeout:90000});
 await node.getByTestId('multiselect_str_labels').click();
 await page.getByRole('option',{name:'backend',exact:true}).click();await page.keyboard.press('Escape');
 await expect(status).toHaveText('1 matching issues.',{timeout:90000});
 await node.getByTestId('dropdown_str_issue_choice').click();
 await page.getByRole('option',{name:'#3 Task 3',exact:true}).click();
 await expect(status).toHaveText('1 matching issues.',{timeout:90000});
 await expect(node.getByTestId('multiselect_str_labels')).toContainText('backend');
 let release,observed;const held=new Promise(r=>{release=r});const seen=new Promise(r=>{observed=r});
 await page.route('**/api/v1/custom_component/update*',async route=>{
   const body=route.request().postDataJSON();
   if(body.field==='repository_url' && body.field_value==='https://github.com/owner/repo/'){
     const response=await route.fetch();observed();await held;await route.fulfill({response});
   }else await route.continue();
 });
 await input.fill('https://github.com/owner/repo/');await input.press('Tab');
 await Promise.race([seen,new Promise((_,reject)=>setTimeout(()=>reject(Error('stale request not observed')),15000))]);
 await input.fill('https://github.com/owner/other');await input.press('Tab');
 await expect(status).toContainText('GitHub discovery failed. Check connection and refresh.',{timeout:90000});
 release();await page.waitForTimeout(1000);
 await expect(status).toContainText('GitHub discovery failed. Check connection and refresh.');
 await expect(node.getByTestId('dropdown_str_issue_choice')).not.toContainText('#3');
 await expect(node.getByText('research',{exact:true})).toHaveCount(0);
 await expect(node.getByText('backend',{exact:true})).toHaveCount(0);
 console.log('PASS: repository change clears dependent selections; held old response cannot restore them. No build or provider calls.');
})().catch(e=>{console.error(e.message);process.exitCode=1}).finally(async()=>{if(browser)await browser.close()});
