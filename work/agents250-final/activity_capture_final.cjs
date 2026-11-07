const fs=require('fs'),path=require('path');
const {chromium,expect}=require('C:/Users/Amadou/AppData/Local/Temp/lfui-dsby42ay/lf/src/frontend/node_modules/@playwright/test');
(async()=>{
 const e='C:/CodeWorkspace/laomedo/claude-review.local/agents-250-20261107',state=JSON.parse(fs.readFileSync(path.join(e,'runtime-path.json'))).path;
 const graphs=JSON.parse(fs.readFileSync(path.join(e,'live-graphs.json'))).filter(g=>g.provider==='opencode'),browser=await chromium.launch({channel:'msedge',headless:true}),results=[];
 try{
 const context=await browser.newContext({viewport:{width:1600,height:1100},storageState:path.join(state,'browser-state.json')}),page=await context.newPage();
 for(const graph of graphs){
  const errors=[];const listener=err=>errors.push(err.message);page.on('pageerror',listener);
  await page.goto(graph.url);await page.getByTestId('sidebar-nav-agents').waitFor({timeout:90000});
  await page.getByTestId('sidebar-nav-agents').click();
  const activity=page.getByRole('region',{name:'Graph agent activity'});await activity.waitFor();
  await expect(page.getByTestId('agent-timeline-row').first()).toBeVisible({timeout:30000});
  await page.getByTestId('agent-timeline-row').first().getByRole('button').first().click();
  await expect(page.getByRole('article',{name:'Selected agent run'})).toBeVisible();
  await page.waitForTimeout(1000);
  await page.screenshot({path:path.join(e,graph.provider+'-capture-final-activity.png')});
  const text=await activity.innerText();
  fs.writeFileSync(path.join(e,graph.provider+'-capture-final-activity-visible.txt'),text);
  results.push({provider:graph.provider,graph:graph.url,timeline_rows:await page.getByTestId('agent-timeline-row').count(),turn_bars:await page.getByTestId('agent-turn-bar').count(),has_actual_heading:text.includes('laomedo'),captured_state:(text.match(/Captured stream:\s*(\w+)/)||[])[1],page_errors:errors});
  console.log(JSON.stringify(results.at(-1)));page.off('pageerror',listener);
 }
 fs.writeFileSync(path.join(e,'capture-final-activity-browser-results.json'),JSON.stringify(results,null,2));
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1});
