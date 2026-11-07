const fs = require('fs'), path = require('path');
const {chromium, expect} = require('C:/Users/Amadou/AppData/Local/Temp/lfui-dsby42ay/lf/src/frontend/node_modules/@playwright/test');
(async () => {
  const e = 'C:/CodeWorkspace/laomedo/claude-review.local/github-249-20261106';
  const state = JSON.parse(fs.readFileSync(path.join(e,'runtime-path.json'))).path;
  const graph = JSON.parse(fs.readFileSync(path.join(e,'live-feedback-graph.json')));
  const b = await chromium.launch({channel:'msedge',headless:true});
  try {
    const c = await b.newContext({viewport:{width:1600,height:1100},storageState:path.join(state,'browser-state.json')});
    const p = await c.newPage(); await p.goto(graph.url);
    await p.locator('.react-flow__node[data-id="agent"]').waitFor({timeout:90000});
    const before = await (await p.request.get('http://127.0.0.1:17862/api/v1/flows/'+graph.id)).json();
    const edges = JSON.stringify(before.data.edges);
    before.data.nodes.find(n=>n.id==='agent').position = {x:600,y:680};
    const updated = await p.request.patch('http://127.0.0.1:17862/api/v1/flows/'+graph.id,{data:{data:before.data}});
    if (!updated.ok()) throw Error('layout_update_'+updated.status());
    await p.reload(); await p.locator('.react-flow__node[data-id="agent"]').waitFor({timeout:90000});
    await p.getByTestId('canvas_controls_dropdown').click(); await p.getByTestId('fit_view').click();
    await p.getByTestId('zoom_out').click(); await p.keyboard.press('Escape');
    await expect.poll(async()=>p.locator('.react-flow__node').evaluateAll(nodes=>nodes.length===3 && nodes.every(n=>{const r=n.getBoundingClientRect();return r.top>75&&r.bottom<1040&&r.left>290&&r.right<1590;})),{timeout:10000}).toBe(true);
    await p.locator('.react-flow__pane').click({position:{x:40,y:40}});
    await p.screenshot({path:path.join(e,'final-feedback-graph-clear.png')});
    const after = await (await p.request.get('http://127.0.0.1:17862/api/v1/flows/'+graph.id)).json();
    if (JSON.stringify(after.data.edges)!==edges) throw Error('layout_changed_edges');
    const record={head:'39aef3ebfcd7a8480433687f2aaff155823dcf55',runtime_head:'3786201298fe729ddf3d315c2d70e4b079a8c36b',url:graph.url,change:'Agent y80 to680 only, native Fit followed by Zoom Out',edges_unchanged:true,node_count:3,all_nodes_inside_viewport_with_margin:true,no_graph_execution:true};
    fs.writeFileSync(path.join(e,'layout-verification.json'),JSON.stringify(record,null,2));
    console.log(JSON.stringify(record));
  } finally {await b.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
