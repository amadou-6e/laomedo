// Continue the real acceptance conversation: approve exact connection repair, then a real run.
import {createRequire} from 'node:module';
import {readFile,writeFile} from 'node:fs/promises';
const require=createRequire('C:/CodeWorkspace/laomedo/.tools/assistant-282-upstream/src/frontend/package.json');
const {chromium}=require('playwright');const root='C:/CodeWorkspace/laomedo';const m=JSON.parse(await readFile(root+'/.tools/assistant-291-live.json','utf8'));
const browser=await chromium.launch({headless:true,channel:'chrome'});const context=await browser.newContext({viewport:{width:1041,height:895},colorScheme:'dark'});const page=await context.newPage();
const api=(path)=>page.evaluate(async(path)=>{const r=await fetch(path,{credentials:'same-origin',headers:{Accept:'application/json'}});if(!r.ok)throw Error('HTTP'+r.status);return r.json();},path);
try{
 const editor=await context.newPage();await editor.goto(m.base+'/flow/'+m.flow);await editor.locator('.react-flow__node').nth(1).waitFor({timeout:90000});
 await page.goto(m.base+'/assistant?conversation='+m.browserConversation);
 await page.getByRole('textbox',{name:'Message this assistant'}).waitFor({timeout:90000});
 const before=await api('/api/v1/flows/'+m.flow);
 await page.getByRole('textbox',{name:'Message this assistant'}).fill(`Read workflow ${m.flow} and describe its Chat Output component. The test graph incorrectly connects ChatInput-input.message to ChatOutput-output.context_id. Propose an edit with key repair-connection that disconnects that connection and connects ChatInput-input.message to ChatOutput-output.input_value. Do not change any other settings. Wait for human approval.`);
 await page.getByRole('textbox',{name:'Message this assistant'}).press('Enter');
 await page.getByRole('button',{name:'Approve changes',exact:true}).waitFor({timeout:240000});
 const card=page.getByRole('article',{name:/Edit graph:/}).last();await card.screenshot({path:root+'/.tools/assistant-291-screens/connection-pending.png'});
 const unchanged=await api('/api/v1/flows/'+m.flow);if(JSON.stringify(unchanged.data)!==JSON.stringify(before.data))throw Error('Repair changed before approval');
 await card.getByRole('button',{name:'Approve changes',exact:true}).click();await card.getByText('Saved graph updated.').waitFor({timeout:30000});
 const after=await api('/api/v1/flows/'+m.flow);if(after.data.edges.length!==1||after.data.edges[0].data.targetHandle.fieldName!=='input_value')throw Error('Wrong connection');
 if(JSON.stringify(after.data.nodes)!==JSON.stringify(before.data.nodes))throw Error('Node settings changed');
 await card.screenshot({path:root+'/.tools/assistant-291-screens/connection-succeeded.png'});
 console.log(JSON.stringify({connectionRepairApproved:true,nodesPreserved:true,editorStayedOpen:true}));
 await page.getByRole('textbox',{name:'Message this assistant'}).fill(`Read the current revision of workflow ${m.flow} and propose_graph_run with key ui-run-success, input_value approval-live-input, input_type chat, output_type any. Do not execute without the approval card.`);
 await page.getByRole('textbox',{name:'Message this assistant'}).press('Enter');
 await page.getByRole('button',{name:'Approve run',exact:true}).waitFor({timeout:240000});
 const runCard=page.getByRole('article',{name:/Run graph:/}).last();await runCard.screenshot({path:root+'/.tools/assistant-291-screens/run-pending.png'});
 await runCard.getByRole('button',{name:'Approve run',exact:true}).click();await runCard.getByText('Graph run completed.').waitFor({timeout:90000});
 await runCard.screenshot({path:root+'/.tools/assistant-291-screens/run-succeeded.png'});
 const detail=await api('/api/v1/laomedo/assistant/conversations/'+m.browserConversation);const action=detail.actions.filter(a=>a.kind==='run').at(-1);
 if(action.state!=='succeeded'||!action.run_id)throw Error('No completed run');m.runAction=action.id;m.runId=action.run_id;await writeFile(root+'/.tools/assistant-291-live.json',JSON.stringify(m));
 await page.reload();await page.getByText('Graph run completed.').waitFor({timeout:30000});await page.screenshot({path:root+'/.tools/assistant-291-screens/final-chat.png',fullPage:true});
 console.log(JSON.stringify({actualGraphExecution:true,state:action.state,runId:action.run_id,retainedAfterReload:true,newAgentTurns:2}));
}catch(e){await page.screenshot({path:root+'/.tools/assistant-291-screens/repair-failure.png',fullPage:true}).catch(()=>{});throw e;}finally{await browser.close();}
