/** Real profile-authenticated browser campaign. No credentials or raw chats in evidence. */
import { createRequire } from 'node:module';
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
const require = createRequire('C:/CodeWorkspace/laomedo/.tools/assistant-282-upstream/src/frontend/package.json');
const { chromium } = require('playwright');
const root = 'C:/CodeWorkspace/laomedo';
const base = 'http://127.0.0.1:55753';
const campaign = process.env.CAMPAIGN_ID ?? `stability-${Date.now()}`;
const directory = path.join(root, '.tools', campaign);
fs.mkdirSync(directory, { recursive: true });
const browser = await chromium.launch({headless:true,executablePath:'C:/Users/amado/AppData/Local/ms-playwright/chromium-1248/chrome-win64/chrome.exe'});
const context = await browser.newContext({baseURL:base, extraHTTPHeaders:{Origin:base}, viewport:{width:1280,height:960}});
const pin = fs.readFileSync(path.join(root,'.env'),'utf8').split(/\r?\n/).find(line=>line.startsWith('LAOMEDO_PIN='))?.slice('LAOMEDO_PIN='.length).trim().replace(/^['"]|['"]$/g,'');
const profiles = await (await context.request.get('/api/v1/laomedo/profiles')).json();
const profile = profiles.profiles.find(item=>item.name.toLowerCase()==='amadou') ?? profiles.profiles[0];
if (!pin || !profile) throw Error('profile_login_input_absent');
const login = await context.request.post('/api/v1/login',{form:{username:profile.name,password:pin}});
if (!login.ok()) throw Error(`profile_login_${login.status()}`);
// Cookies remain in this temporary browser context; never persist storage state.
async function api(endpoint,body) {
 const response = await context.request[body===undefined?'get':'post']('/api/v1/laomedo/assistant'+endpoint,body===undefined?{}:{data:body});
 const value = await response.json();
 if(!response.ok()) throw Error(`${endpoint}:${response.status()}:${value.detail?.code??value.code??'request_failed'}`);
 return value;
}
const page = await context.newPage();
if(process.env.INSPECT_ONLY==='1') {
 const index = await api('/conversations');
 for(const row of index.conversations.filter(item=>item.updated_at>Date.now()/1000-4000)) {
  const detail=await api('/conversations/'+row.id);
  console.log(JSON.stringify({id:row.id,provider:row.provider,state:detail.conversation.state,active:detail.conversation.active_message_id,error:detail.conversation.error_code,observation:detail.observation_error,messages:detail.messages.map(m=>({state:m.state,error:m.error_code,native:!!m.native_action_id})),native:detail.native_actions?.map(a=>({name:a.name,state:a.state}))}));
 }
 await browser.close();process.exit(0);
}
const seed=crypto.randomBytes(4).readUInt32LE();let random=seed;
function choose(items){random=(Math.imul(random,1664525)+1013904223)>>>0;return items[random%items.length];}
const report={campaign,seed,revision:process.env.TEST_REVISION??'unknown',started:new Date().toISOString(),cases:[]};
function save(){fs.writeFileSync(path.join(directory,'report.json'),JSON.stringify(report,null,2));}
async function settled(id,previousCount) {
 const deadline=Date.now()+240000;
 while(Date.now()<deadline) {
  const detail=await api('/conversations/'+id);
  if(detail.messages.length>previousCount&&!detail.conversation.active_message_id&&!['starting','running','stopping'].includes(detail.conversation.state)) {
   const last=detail.messages.at(-1);
   if(detail.conversation.state!=='idle'||last.state!=='completed') throw Error(`terminal:${detail.conversation.state}:${last.state}:${last.error_code??detail.conversation.error_code??''}`);
   return detail;
  }
  await page.waitForTimeout(1000);
 }
 throw Error('turn_deadline_no_automatic_replay');
}
async function send(id,text,command=false) {
 const before=await api('/conversations/'+id);
 const box=page.getByRole('textbox',{name:'Message this assistant',exact:true});
 await box.fill(text);
 const send=page.getByRole('button',{name:'Send',exact:true});
 await send.waitFor({timeout:20000});
 const deadline=Date.now()+25000;
 while(await send.isDisabled()&&Date.now()<deadline) await page.waitForTimeout(200);
 if(await send.isDisabled()) throw Error('send_stuck_disabled_before_dispatch');
 await send.click();
 const detail=await settled(id,before.messages.length);
 await box.fill('NEXT-DRAFT-NOT-SENT');
 const recovery=Date.now()+10000;
 while(await send.isDisabled()&&Date.now()<recovery) await page.waitForTimeout(200);
 if(await send.isDisabled()) throw Error('send_stuck_disabled_after_terminal');
 await box.fill('');
 return {state:detail.messages.at(-1).state,command,reply:command?undefined:detail.messages.at(-1).response};
}
try {
 const connections=(await api('/connections')).connections;
 const providers=['codex','claude','opencode'];
 for(let index=0;index<Number(process.env.CASE_COUNT??20);index++) {
  const provider=providers[index%3];
  const item={number:index+1,provider,steps:[],state:'running'};report.cases.push(item);save();
  try {
   const account=connections.find(c=>c.provider===provider&&c.lifecycle==='connected');
   if(!account)throw Error('provider_account_absent');
   const query=new URLSearchParams({provider,connection_id:account.connection_id,connection_generation:String(account.generation)});
   const models=(await api('/models?'+query)).models;
   const model=models.find(m=>m.id===(provider==='codex'?'gpt-6.1-sol':provider==='claude'?'sonnet':'opencode-go/gpt-6-luna'))??models[0];
   const effort=model.efforts.includes('low')?'low':model.efforts[0];
   const conversation=await api('/conversations',{provider,connection_id:account.connection_id,connection_generation:account.generation,model:model.id,effort});
   item.id=conversation.id;item.model=model.id;save();
   await page.goto(base+'/assistant?conversation='+conversation.id);
   const marker=`STABILITY-${index+1}-${campaign.slice(-6)}`;
   const initial=await send(conversation.id,`Remember marker ${marker}. Reply only with this marker. Do not use tools.`);
   if(!initial.reply?.includes(marker))throw Error('initial_marker_missing');
   item.steps.push({operation:'initial',state:initial.state});save();
   const catalog=await api('/conversations/'+conversation.id+'/native-commands');
   const options=catalog.commands.filter(c=>c.executable&&!['login','logout','connect','rename'].includes(c.name));
   if(!options.length)throw Error('no_executable_native_commands');
   const count=Number(process.env.COMMAND_COUNT??1);
   for(let turn=0;turn<count;turn++) {
    const entry=choose(options);
    const prefix=entry.name.startsWith('$')?'':'/';
    const args=entry.kind==='skill'&&entry.accepts_arguments?' Explain the purpose of this skill in one sentence. Do not create files or use tools.':'';
    const result=await send(conversation.id,prefix+entry.name+args,true);
    item.steps.push({operation:entry.name,state:result.state});save();
    const follow=await send(conversation.id,`Reply only with the original validation marker. Do not use tools.`);
    if(!follow.reply?.includes(marker))throw Error('resume_marker_missing');
    item.steps.push({operation:'followup',state:follow.state});save();
   }
   // Reload and ensure a real next user turn remains possible after history rebind.
   await page.reload();
   const final=await send(conversation.id,`Reply exactly DONE-${marker}. Do not use tools.`);
   if(!final.reply?.includes('DONE-'+marker))throw Error('reload_followup_marker_missing');
   item.steps.push({operation:'reload_followup',state:final.state});item.state='passed';save();
   console.log(JSON.stringify({case:index+1,provider,state:item.state,commands:item.steps.filter(s=>!['initial','followup','reload_followup'].includes(s.operation)).map(s=>s.operation)}));
  }catch(error){item.state='failed';item.error=error.message;save();await page.screenshot({path:path.join(directory,`failure-${index+1}.png`)});console.log(JSON.stringify({case:index+1,provider,state:'failed',error:error.message}));throw error;}
 }
 report.state='passed';
}catch(error){report.state='failed';report.error=error.message;process.exitCode=1;}
finally {report.finished=new Date().toISOString();save();await browser.close();}
