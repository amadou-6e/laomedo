// Real native pending cards and human grant panel on a dedicated disposable graph.
import {createRequire} from 'node:module';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
const require=createRequire('C:/CodeWorkspace/laomedo/.tools/assistant-282-upstream/src/frontend/package.json');
const {chromium}=require('playwright');
const root='C:/CodeWorkspace/laomedo';
const m=JSON.parse(await readFile(root+'/.tools/assistant-291-live.json','utf8'));
const browser=await chromium.launch({headless:true,channel:'chrome'});
const context=await browser.newContext({viewport:{width:1041,height:895},colorScheme:'dark'});
const page=await context.newPage();
const api=async(path,body)=>page.evaluate(async({path,body})=>{
 const r=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});
 if(!r.ok)throw Error('HTTP '+r.status+' '+path);return r.json();
},{path,body});
try {
 await page.goto(m.base+'/assistant');
 await page.getByRole('button',{name:'New conversation',exact:true}).waitFor({timeout:90000});
 const source=await api('/api/v1/flows/'+m.flow);
 const graph=await api('/api/v1/flows/',{name:'Approval visual review '+Date.now(),data:source.data});
 const models=await api('/api/v1/laomedo/assistant/models');
 const model=models.models.find(x=>x.id==='gpt-6-luna')??models.models[0];
 const chat=await api('/api/v1/laomedo/assistant/conversations',{provider:'codex',model:model.id,effort:model.efforts[0]});
 await writeFile(root+'/.tools/assistant-final-review-live.json',JSON.stringify({conversation:chat.id,flow:graph.id}));
 await page.goto(m.base+'/assistant?conversation='+chat.id);
 const prompt=`Inspect workflow ${graph.id} using Laomedo. Propose three SEPARATE actions on its exact current revision: rename to Approval visual renamed with key visual-rename; change only ChatInput-input.input_value to visual-input with key visual-edit and summary Change the input text to visual-input; run with input_value visual-run-input, input_type chat, output_type any, key visual-run and summary Run with input visual-run-input. Do not grant permissions or use alternate APIs. Leave all decisions to the app. Reply briefly.`;
 await page.getByRole('textbox',{name:'Message this assistant'}).fill(prompt);
 await page.getByRole('textbox',{name:'Message this assistant'}).press('Enter');
 for(const label of ['Always approve renames','Always approve edits','Always approve runs'])await page.getByRole('button',{name:label,exact:true}).waitFor({timeout:240000});
 const dir=root+'/.tools/assistant-final-cards';await mkdir(dir,{recursive:true});
 for(const [category,label] of [['rename','Always approve renames'],['edit','Always approve edits'],['run','Always approve runs']]){
  const card=page.getByRole('article').filter({has:page.getByRole('button',{name:label,exact:true})});
  await card.screenshot({path:dir+'/'+category+'-pending.png'});
 }
 const before=await api('/api/v1/flows/'+graph.id);
 if(before.name!==graph.name||JSON.stringify(before.data)!==JSON.stringify(source.data))throw Error('Graph changed before approval');
 await page.getByRole('button',{name:'Always approve renames',exact:true}).click();
 await page.getByRole('complementary',{name:'Conversation approvals'}).waitFor({timeout:30000});
 await page.getByRole('complementary',{name:'Conversation approvals'}).screenshot({path:dir+'/permissions.png'});
 const changed=await api('/api/v1/flows/'+graph.id);
 if(changed.name!=='Approval visual renamed'||JSON.stringify(changed.data)!==JSON.stringify(source.data))throw Error('Unexpected approved change');
 await page.getByRole('button',{name:'Ask every time for rename'}).click();
 await page.getByRole('complementary',{name:'Conversation approvals'}).waitFor({state:'detached'});
 const final=await api('/api/v1/laomedo/assistant/conversations/'+chat.id);
 if(final.permissions.length||final.actions.some(x=>x.kind==='run'&&x.state!=='pending'))throw Error('Unexpected grant or run');
 console.log(JSON.stringify({realNativeProposal:true,pendingCards:3,graphUnchangedBeforeApproval:true,humanRenameOnly:true,permissionPanelCaptured:true,revokedAtEnd:true,noGraphRun:true}));
} catch(error){await page.screenshot({path:root+'/.tools/assistant-review-visual-failure.png'}).catch(()=>{});throw error;} finally {await browser.close();}
