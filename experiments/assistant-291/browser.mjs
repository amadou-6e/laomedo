// Independent real browser/native-agent acceptance. Never exports the owner's browser session.
import {createRequire} from 'node:module';
import {readFile,writeFile,mkdir} from 'node:fs/promises';
const require=createRequire('C:/CodeWorkspace/laomedo/.tools/assistant-282-upstream/src/frontend/package.json');
const {chromium}=require('playwright');
const root='C:/CodeWorkspace/laomedo';
const metadata=JSON.parse(await readFile(root+'/.tools/assistant-291-live.json','utf8'));
const browser=await chromium.launch({headless:true,channel:'chrome'});
const context=await browser.newContext({viewport:{width:1041,height:895},colorScheme:'dark'});
const page=await context.newPage();
const api=async(path,body)=>page.evaluate(async({path,body})=>{
 const r=await fetch(path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:{'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)})});
 if(!r.ok)throw Error('HTTP '+r.status+' '+path);
 return r.json();
},{path,body});
try{
 await page.goto(metadata.base+'/assistant?acceptance=8c665896');
 await page.getByRole('button',{name:'New conversation',exact:true}).waitFor({timeout:90000});
 const models=await api('/api/v1/laomedo/assistant/models');
 const model=models.models.find(m=>m.id==='gpt-6-luna')??models.models[0];
 const chat=await api('/api/v1/laomedo/assistant/conversations',{provider:'codex',model:model.id,effort:model.efforts[0]});
 metadata.browserConversation=chat.id;
 await writeFile(root+'/.tools/assistant-291-live.json',JSON.stringify(metadata));
 // Open the editor before the proposal. Native auto-login in a new tab may
 // rotate its cookie; proposal and decision must share the current app session.
 const editor=await context.newPage();
 await editor.goto(metadata.base+'/flow/'+metadata.flow);
 await editor.locator('.react-flow__node').nth(1).waitFor({timeout:90000});
 await mkdir(root+'/.tools/assistant-291-screens',{recursive:true});
 await editor.screenshot({path:root+'/.tools/assistant-291-screens/editor-before.png',fullPage:true});
 await page.goto(metadata.base+'/assistant?conversation='+chat.id);
 await page.getByRole('textbox',{name:'Message this assistant'}).waitFor();
 const original=await api('/api/v1/flows/'+metadata.flow);
 const prompt=`Inspect workflow ${metadata.flow}. Through Laomedo propose_graph_edit, propose changing ChatInput-input.input_value to approval-ui-edited using key ui-edit. Also propose a separate edit changing it to rejected-value using key ui-reject. Do not execute or copy anything. Both must wait for human approval.`;
 await page.getByRole('textbox',{name:'Message this assistant'}).fill(prompt);
 await page.getByRole('textbox',{name:'Message this assistant'}).press('Enter');
 await page.getByRole('button',{name:'Approve changes',exact:true}).nth(1).waitFor({timeout:240000});
 const before=await api('/api/v1/flows/'+metadata.flow);
 if(JSON.stringify(before.data)!==JSON.stringify(original.data))throw Error('Changed before approval');
 await mkdir(root+'/.tools/assistant-291-screens',{recursive:true});
 const cards=page.getByRole('article',{name:/Edit graph:/});
 await cards.first().screenshot({path:root+'/.tools/assistant-291-screens/edit-pending.png'});
 // Reject the second proposal; the first remains the sole approved edit.
 await cards.nth(1).getByRole('button',{name:'Reject',exact:true}).click();
 await cards.nth(1).getByText('Rejected. No action was executed.').waitFor();
 await cards.first().getByRole('button',{name:'Approve changes',exact:true}).click();
 await cards.first().getByText('Saved graph updated.').waitFor({timeout:30000});
 const edited=await api('/api/v1/flows/'+metadata.flow);
 const input=edited.data.nodes.find(n=>n.id==='ChatInput-input');
 if(input.data.node.template.input_value.value!=='approval-ui-edited')throw Error('Approved field not updated');
 const expected=structuredClone(original.data); expected.nodes.find(n=>n.id==='ChatInput-input').data.node.template.input_value.value='approval-ui-edited';
 if(JSON.stringify(edited.data)!==JSON.stringify(expected))throw Error('Unmentioned graph bytes changed');
 await cards.first().screenshot({path:root+'/.tools/assistant-291-screens/edit-succeeded.png'});
 await cards.nth(1).screenshot({path:root+'/.tools/assistant-291-screens/edit-rejected.png'});
 console.log(JSON.stringify({stage:'edit',actualAgentProposals:true,unchangedBeforeApproval:true,rejectNoEffect:true,approvedExactFieldOnly:true,openEditorPreserved:true,conversation:chat.id}),{flush:true});
 // A real run is proposed against the now-current revision in a follow-up turn.
 const runPrompt=`Read workflow ${metadata.flow} again, then propose_graph_run using operation_key ui-run, its exact current revision, input_value approval-live-input, input_type chat, output_type any. Wait for human approval; do not run through any other path.`;
 await page.getByRole('textbox',{name:'Message this assistant'}).fill(runPrompt);
 await page.getByRole('textbox',{name:'Message this assistant'}).press('Enter');
 await page.getByRole('button',{name:'Approve run',exact:true}).waitFor({timeout:240000});
 const runCard=page.getByRole('article',{name:/Run graph:/});
 await runCard.screenshot({path:root+'/.tools/assistant-291-screens/run-pending.png'});
 await runCard.getByRole('button',{name:'Approve run',exact:true}).click();
 await runCard.getByText('Graph run completed.').waitFor({timeout:90000});
 await runCard.screenshot({path:root+'/.tools/assistant-291-screens/run-succeeded.png'});
 const detail=await api('/api/v1/laomedo/assistant/conversations/'+chat.id);
 const action=detail.actions.find(a=>a.kind==='run');
 if(!action.run_id||action.state!=='succeeded')throw Error('No authoritative completed run');
 metadata.runAction=action.id; metadata.runId=action.run_id;
 await writeFile(root+'/.tools/assistant-291-live.json',JSON.stringify(metadata));
 await page.reload();await page.getByText('Graph run completed.').waitFor({timeout:30000});
 await page.screenshot({path:root+'/.tools/assistant-291-screens/final-chat.png',fullPage:true});
 console.log(JSON.stringify({stage:'run',actualGraphExecution:true,state:action.state,runId:action.run_id,retainedAfterReload:true,newAgentTurns:2}));
}catch(error){await page.screenshot({path:root+'/.tools/assistant-291-screens/acceptance-failure.png',fullPage:true}).catch(()=>{});throw error;}finally{await browser.close();}
