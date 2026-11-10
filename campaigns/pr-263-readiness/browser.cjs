const path=require('path');const crypto=require('crypto');
const runtime=path.join(process.env.TEMP,'laomedo-graph-20261107');
const {chromium}=require(path.join(runtime,'upstream-langflow/src/frontend/node_modules/@playwright/test'));
const out=path.join(process.cwd(),'.tools/pr-readiness');
(async()=>{const context=await chromium.launchPersistentContext(path.join(runtime,'readiness/profile-browser'),{channel:'msedge',headless:true,viewport:{width:1280,height:900}});try{
const page=context.pages()[0]||await context.newPage();await page.goto('http://127.0.0.1:17866/login',{waitUntil:'domcontentloaded'});
await page.getByRole('heading',{name:'No profiles yet',exact:true}).waitFor({timeout:60000});await page.screenshot({path:path.join(out,'263-empty.png'),fullPage:true});
await page.getByRole('button',{name:/^create profile$/i}).click();await page.getByLabel('Profile name',{exact:true}).fill('Readiness QA');await page.screenshot({path:path.join(out,'263-create.png'),fullPage:true});
const pin='0'+String(crypto.randomInt(10000,100000));await page.getByLabel('PIN (6 digits)',{exact:true}).fill(pin);await page.getByLabel('Confirm PIN',{exact:true}).fill(pin);
let registrationStatus,loginStatus;page.on('response',r=>{const p=new URL(r.url()).pathname;if(p==='/api/v1/laomedo/profiles'&&r.request().method()==='POST')registrationStatus=r.status();if(p==='/api/v1/login')loginStatus=r.status();});
await page.getByRole('button',{name:/^create profile$/i}).click();await page.waitForURL('http://127.0.0.1:17866/',{timeout:45000});
await page.getByTestId('empty_page_github_button').waitFor({timeout:30000});await page.screenshot({path:path.join(out,'263-entered.png'),fullPage:true});console.log(JSON.stringify({phase:'created',registrationStatus,loginStatus}));
let trackingWrites=0;page.on('request',r=>{if(r.method()==='PATCH'&&new URL(r.url()).pathname.startsWith('/api/v1/users/'))trackingWrites++;});
const popupPromise=context.waitForEvent('page');await page.getByTestId('empty_page_github_button').click();const popup=await popupPromise;await popup.close();await page.waitForTimeout(2000);console.log(JSON.stringify({phase:'community-link',popupOpened:true,trackingWrites}));
await page.reload();await page.getByTestId('empty_page_github_button').waitFor({timeout:30000});console.log(JSON.stringify({phase:'reload',restored:true}));
}finally{await context.close();}})().catch(e=>{console.error(e.message);process.exit(1)});
