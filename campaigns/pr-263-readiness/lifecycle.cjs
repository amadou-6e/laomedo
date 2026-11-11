const path=require('path'),fs=require('fs'),crypto=require('crypto');
const runtime=path.join(process.env.TEMP,'laomedo-graph-20261107');
const {chromium}=require(path.join(runtime,'upstream-langflow/src/frontend/node_modules/@playwright/test'));
const out=path.join(process.cwd(),'.tools/pr-readiness');
(async()=>{const context=await chromium.launchPersistentContext(path.join(runtime,'readiness/profile-lifecycle-browser'),{channel:'msedge',headless:true,viewport:{width:1280,height:900}});try{
const page=context.pages()[0]||await context.newPage();const base='http://127.0.0.1:17866';
await page.goto(base+'/login');await page.getByRole('heading',{name:/^(no profiles yet|choose profile)$/i}).waitFor({timeout:60000});
await page.getByRole('button',{name:/^create (another )?profile$/i}).click();
const name='Lifecycle QA '+Date.now();const pin='0'+String(crypto.randomInt(10000,100000));
await page.getByLabel('Profile name',{exact:true}).fill(name);await page.getByLabel('PIN (6 digits)',{exact:true}).fill(pin);await page.getByLabel('Confirm PIN',{exact:true}).fill(pin);
await page.getByRole('button',{name:/^create profile$/i}).click();await page.waitForURL(base+'/',{timeout:60000});await page.getByTestId('user-profile-settings').waitFor();
console.log(JSON.stringify({phase:'created',authenticated:true}));
fs.writeFileSync(path.join(out,'263-lifecycle-await-restart.json'),JSON.stringify({ready:true}));
for(let i=0;i<240&&!fs.existsSync(path.join(out,'263-lifecycle-restarted.json'));i++)await page.waitForTimeout(1000);
if(!fs.existsSync(path.join(out,'263-lifecycle-restarted.json')))throw Error('Timed out waiting for task-owned app restart');
await page.reload();await page.getByTestId('user-profile-settings').waitFor({timeout:60000});console.log(JSON.stringify({phase:'actual-app-restart',restored:true}));
// A real cross-document navigation: record persisted status without synthesizing pageshow.
await page.evaluate(()=>window.addEventListener('pageshow',e=>sessionStorage.setItem('qa-pageshow-persisted',String(e.persisted))));
await page.goto('about:blank');await page.goBack({waitUntil:'domcontentloaded'});await page.getByTestId('user-profile-settings').waitFor({timeout:60000});
const persisted=await page.evaluate(()=>sessionStorage.getItem('qa-pageshow-persisted'));
console.log(JSON.stringify({phase:'back-navigation',authenticated:true,persisted}));
// Force a genuine persisted event only as a separate supporting mechanism check.
const navigation=page.waitForEvent('framenavigated',f=>f===page.mainFrame());
await page.evaluate(()=>window.dispatchEvent(new PageTransitionEvent('pageshow',{persisted:true})));await navigation;await page.getByTestId('user-profile-settings').waitFor();
console.log(JSON.stringify({phase:'persisted-event-supporting-only',reloaded:true}));
await page.screenshot({path:path.join(out,'263-lifecycle-restored.png'),fullPage:true});
}finally{await context.close();}})().catch(e=>{console.error(e.message);process.exit(1)});
