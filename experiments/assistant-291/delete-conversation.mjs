// Create and delete only a fresh empty acceptance chat. Preserve existing chats and saved workflows.
import {createRequire} from 'node:module';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
const require=createRequire('C:/CodeWorkspace/laomedo/.tools/assistant-282-upstream/src/frontend/package.json');
const {chromium}=require('playwright');
const root='C:/CodeWorkspace/laomedo';
const m=JSON.parse(await readFile(root+'/.tools/assistant-291-live.json','utf8'));
const browser=await chromium.launch({headless:true,channel:'chrome'});
try {
 const context=await browser.newContext({viewport:{width:1041,height:895},colorScheme:'dark'});
 const page=await context.newPage();
 await page.goto(m.base+'/assistant');
 await page.getByRole('button',{name:'New conversation',exact:true}).waitFor({timeout:90000});
 const api=async(path,body,method)=>page.evaluate(async({path,body,method})=>{const r=await fetch(path,{method:method??(body===undefined?'GET':'POST'),credentials:'same-origin',headers:{'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});if(!r.ok)throw Error('HTTP '+r.status);return r.json();},{path,body,method});
 if(process.argv.includes('--check-active')) { const listing=await api('/api/v1/laomedo/assistant/conversations'); let active=0; for(const chat of listing.conversations) { if(chat.active_message_id) active++; const detail=await api('/api/v1/laomedo/assistant/conversations/'+chat.id); active+=(detail.actions??[]).filter(x=>x.state==='executing').length; } console.log(JSON.stringify({activeWork:active,checkedConversations:listing.conversations.length,hasMore:listing.next_cursor!==null})); } else {
 const original=await api('/api/v1/flows/'+m.flow);
 const models=await api('/api/v1/laomedo/assistant/models');
 const model=models.models.find(x=>x.id==='gpt-6-luna')??models.models[0];
 const chat=await api('/api/v1/laomedo/assistant/conversations',{provider:'codex',model:model.id,effort:model.efforts[0]});
 await api('/api/v1/laomedo/assistant/conversations/'+chat.id,{title:'Delete acceptance conversation'},'PATCH');
 await page.goto(m.base+'/assistant?conversation='+chat.id+'&ui=delete');
 await page.getByRole('button',{name:'Delete conversation',exact:true}).waitFor();
 await mkdir(root+'/.tools/assistant-delete-images',{recursive:true});
 await page.screenshot({path:root+'/.tools/assistant-delete-images/header.png'});
 await page.getByRole('button',{name:'Delete conversation',exact:true}).click();
 await page.waitForTimeout(400);
 await mkdir(root+'/.tools/assistant-delete-images',{recursive:true});
 await page.screenshot({path:root+'/.tools/assistant-delete-images/confirmation.png'});
 await page.getByRole('button',{name:'Cancel',exact:true}).click();
 await api('/api/v1/laomedo/assistant/conversations/'+chat.id);
 await page.getByRole('button',{name:'Delete conversation',exact:true}).click();
 await page.getByRole('button',{name:'Delete',exact:true}).click();
 await page.getByRole('button',{name:'Delete conversation',exact:true}).waitFor({state:'detached'});
 const status=await page.evaluate(async(id)=>(await fetch('/api/v1/laomedo/assistant/conversations/'+id,{credentials:'same-origin',headers:{'Content-Type':'application/json'}})).status,chat.id);
 if(status!==404)throw Error('Deleted chat remains accessible');
 const listing=await api('/api/v1/laomedo/assistant/conversations');
 if(listing.conversations.some(x=>x.id===chat.id))throw Error('Deleted chat remains in index');
 const after=await api('/api/v1/flows/'+m.flow);
 if(JSON.stringify(original)!==JSON.stringify(after))throw Error('Saved workflow changed');
 await page.getByRole('dialog').waitFor({state:'hidden'});
 await page.waitForTimeout(400);
 await page.screenshot({path:root+'/.tools/assistant-delete-images/deleted.png'});
 await writeFile(root+'/.tools/assistant-delete-live.json',JSON.stringify({deletedConversation:chat.id}));
 console.log(JSON.stringify({newEmptyChatOnly:true,cancelPreservesChat:true,confirmedDelete:true,readReturns404:true,removedFromIndex:true,savedWorkflowUnchanged:true,noInference:true}));
}
} finally {await browser.close();}
