import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
const base = 'http://127.0.0.1:17875';
const repo = 'C:/CodeWorkspace/laomedo';
const modulePath = process.env.TEMP.replaceAll('\\','/') + '/laomedo-graph-20261107/readiness/pr268-upstream/src/frontend/node_modules/playwright/index.mjs';
const {chromium} = await import(pathToFileURL(modulePath).href);
const browser = await chromium.launch({channel:'msedge',headless:true});
try {
 const context = await browser.newContext({viewport:{width:1600,height:1300}});
 const login = await context.request.get(base + '/api/v1/auto_login');
 if (!login.ok()) throw new Error('Auto login HTTP ' + login.status());
 const payload = await login.json();
 const token = payload.access_token;
 const graph = fs.readFileSync(repo + '/.tools/275/layout-preview-review-graph.json');
 const uploaded = await context.request.post(base + '/api/v1/flows/upload/', {headers:{Authorization:'Bearer ' + token},multipart:{file:{name:'flow.json',mimeType:'application/json',buffer:graph}}});
 if (!uploaded.ok()) throw new Error('Flow upload HTTP ' + uploaded.status() + ' ' + (await uploaded.text()).slice(0,400));
 const flows = await uploaded.json();
 const id = flows[0].id;
 const page = await context.newPage();
 await page.goto(base + '/flow/' + id, {waitUntil:'domcontentloaded',timeout:120000});
 await page.waitForTimeout(15000);
 for (const button of await page.getByRole('button',{name:'Dismiss',exact:true}).all()) { if (await button.isVisible()) await button.click(); }
 await page.screenshot({path:repo+'/.tools/275/layout-preview-default.png',fullPage:true});
 const skill=page.locator('.react-flow__node[data-id="skill"]');
 await skill.getByRole('button',{name:'Advanced settings'}).click();
 await page.waitForTimeout(1500);
 await page.screenshot({path:repo+'/.tools/275/layout-preview-advanced.png',fullPage:true});
 console.log('Skill Edit Request visible:',await skill.getByText('Edit Request',{exact:true}).isVisible().catch(()=>false));
 console.log('Skill Revision visible:',await skill.getByText('Revision',{exact:true}).isVisible().catch(()=>false));
 console.log('Connected Prior Run visible:',await page.locator('.react-flow__node[data-id="resume-agent"]').getByText('Prior Run',{exact:true}).isVisible());
 fs.writeFileSync(repo+'/.tools/275/layout-preview-dom.txt',await page.locator('body').innerText());
 fs.writeFileSync(repo+'/.tools/275/layout-preview-public.json',JSON.stringify({url:base+'/flow/'+id,viewport:{width:1600,height:1300},graph:'.tools/275/layout-preview-review-graph.json',origin:'repository saved nodes, view-only composition, no execution',execution:false},null,2));
 console.log('Preview imported and captured: ' + base + '/flow/' + id);
} finally { await browser.close(); }
