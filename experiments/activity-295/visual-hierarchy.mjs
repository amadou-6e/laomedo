import { chromium } from 'file:///C:/CodeWorkspace/laomedo/.tools/preview/agent-activity-295-upstream/src/frontend/node_modules/playwright/index.mjs';
import { readFileSync } from 'node:fs';
const root='C:/CodeWorkspace/laomedo';
// Component-level visual support only. Never served in the owner's shared tab or written to activity storage.
const d=JSON.parse(readFileSync(root+'/.tools/preview/activity-selector-exp/experiments/activity-selector/chat-history/detail.json','utf8'));
d.run.node_label='VISUAL FIXTURE - nested selection';d.run.execution='fixture-hierarchy';d.run.started='2026-11-18T13:00:00Z';d.run.ended='2026-11-18T13:09:00Z';
d.projection.threads.push({id:'child-review',parent:'sample-main',title:'Child review'});
d.projection.turns.push({id:'child-turn',thread:'child-review',started:'2026-11-18T13:01:00Z',ended:'2026-11-18T13:02:00Z',status:'completed'});
d.projection.items.push({id:'child-answer',thread:'child-review',turn:'child-turn',started:'2026-11-18T13:01:02Z',ended:'2026-11-18T13:01:55Z',item:{type:'agentMessage',text:'Visual fixture only: child conversation scope. No native child agent ran.'}});
d.projection.telemetry=[];
const browser=await chromium.launch({channel:"msedge",headless:true});
try {
 const page=await browser.newPage({viewport:{width:1141,height:895}});
 const endpoint='**/api/v1/laomedo/agent-executions/b4714b72-0639-462f-83f7-19869b372d48*';
 await page.route('**/api/v1/laomedo/agent-executions/**',route=>route.fulfill({json:route.request().url().includes('/codex/sample-chat-history')?d:{runs:[d.run]},headers:{'Cache-Control':'no-store'}}));
 await page.goto('http://127.0.0.1:17921/flow/b4714b72-0639-462f-83f7-19869b372d48',{waitUntil:'domcontentloaded'});
 await page.getByRole('button',{name:'Agents',exact:true}).click();
 await page.getByRole('button',{name:/Child review.*1 turn.*completed/}).click();
 await page.getByText('Visual fixture only: child conversation scope. No native child agent ran.').waitFor();
 await page.screenshot({path:root+'/.tools/pr-readiness/295-style/supporting-child.png'});
 await page.getByRole('button',{name:'Search OpenTelemetry records',exact:true}).click();
 await page.getByRole('button',{name:'Close OpenTelemetry records search',exact:true}).click();
 await page.screenshot({path:root+'/.tools/pr-readiness/295-style/supporting-empty-telemetry.png'});
 console.log('Component-only visual support captured. No saved data or native execution changed.');
} finally {await browser.close();}
