const {chromium,expect}=require('@playwright/test');const fs=require('fs');let browser;
(async()=>{
 const f=JSON.parse(fs.readFileSync(process.argv[2],'utf8'));expect(f.provider).toBe('fake-no-network');
 browser=await chromium.launch({channel:'msedge'});const p=await browser.newPage({viewport:{width:1400,height:1000}});
 await p.goto(f.url);const node=p.locator('.react-flow__node[data-id="close"]');await node.waitFor({timeout:60000});await node.click();
 await expect(p.locator('.react-flow__edge')).toHaveCount(10);
 const build=p.waitForResponse(r=>r.request().method()==='POST'&&new URL(r.url()).pathname.startsWith('/api/v2/workflows'),{timeout:90000});
 await node.getByRole('button',{name:'Run component',exact:true}).click();expect((await build).status()).toBe(200);
 const output=node.locator('[data-testid^="output-inspection-"]');await expect(output).toBeEnabled({timeout:120000});await output.click();
 const dialog=p.getByRole('dialog');await expect(dialog).toContainText('succeeded',{timeout:30000});await expect(dialog).toContainText('closed');
 await expect(dialog).not.toContainText('DUMMY');
 console.log('PASS: actual editor Run component traverses two issue readers, task, skill, native agent, contract routing, confirmed update and close; fake model and GitHub only.');
})().catch(e=>{console.error(e.message);process.exitCode=1}).finally(async()=>{if(browser)await browser.close()});
