import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import GraphAgents, { HighlightedJson, MessageMarkdown, commandTitle, activityTitle, aggregateUsagePoints, RuntimeRecords, UsageCharts, conversationRows, scopedProjection, turnPosition, conversationMatches, conversationDocument, telemetryDocument } from "./index";
import { api } from "@/controllers/API/api";
jest.mock("react-syntax-highlighter",()=>({Prism:({children}:{children:string})=><pre><span>{children}</span></pre>}));
jest.mock("@/controllers/API/api",()=>({api:{get:jest.fn()}}));
jest.mock("@/customization/utils/urls",()=>({getBaseUrl:()=>"/api/v1/"}));
let canvasNodes:unknown[]=[];
let activityTarget:{flowId:string;nodeId:string}|null=null;
const clearTarget=jest.fn(()=>{activityTarget=null});
jest.mock("@/stores/agentActivityStore",()=>({useAgentActivityStore:Object.assign((select:any)=>select({target:activityTarget}),{getState:()=>({clearTarget})})}));
jest.mock("@/stores/flowStore",()=>({__esModule:true,default:(select:(state:unknown)=>unknown)=>select({nodes:canvasNodes})}));
const run=(id:string,execution:string)=>({id,node:`node-${id}`,execution,started:"2026-10-15T10:00:00Z",ended:"2026-10-15T10:00:02Z",status:"completed",stream_state:"complete",event_count:2,native_session:id,model:"gpt-6-luna"});
const projection={turns:[],items:[],threads:[],usage:null,usage_points:[],cost:{amount:null},cost_reason:"Unknown model",telemetry:[],telemetry_coverage:"not observed"};
jest.unmock("react-markdown");
jest.mock("@/components/ui/button",()=>({Button:jest.requireActual("react").forwardRef(({variant,size,ignoreTitleCase,...props}:any,ref:any)=><button ref={ref} {...props}/>)}));
jest.mock("@/components/ui/popover",()=>{const primitive=jest.requireActual("@radix-ui/react-popover");return {Popover:primitive.Root,PopoverTrigger:primitive.Trigger,PopoverContent:primitive.Content};});
jest.mock("@/components/ui/badge",()=>({Badge:({variant,size,...props}:any)=><span {...props}/>}));
// Keep this suite focused on activity behavior; the real code viewer is checked in-browser.
jest.mock("@/components/common/genericIconComponent",()=>({__esModule:true,default:()=> <svg/>}));
jest.mock("@/components/core/codeTabsComponent",()=>({__esModule:true,default:({code}:{code:string})=> <pre><span>{code}</span></pre>}));
beforeEach(()=>{jest.clearAllMocks();canvasNodes=[];activityTarget=null});

test("conversation fuzzy search preserves transcript order and exports exact scope and tool metadata",()=>{
  const items=[
    {id:"a",thread:"child",turn:"t",started:"2026-10-25T07:00:00Z",ended:null,item:{type:"agentMessage",text:"Inspect commandExecution output"}},
    {id:"b",thread:"child",turn:"t",started:"2026-10-25T07:00:01Z",ended:null,item:{type:"commandExecution",command:"echo ```",aggregatedOutput:"```\nprivate result"}},
    {id:"c",thread:"child",turn:"t",started:"2026-10-25T07:00:02Z",ended:null,item:{type:"agentMessage",text:"Other answer"}},
  ];
  const context={graph_id:"graph",run_id:"run",execution_id:"execution",node_id:"node",provider:"opencode",model:"go/model",native_session:"parent",scope:{thread:"child",turn:"t"},capture_state:"complete",truncated:false};
  const filtered=conversationMatches(items,"commndExecution");
  expect(filtered.map(item=>item.id)).toEqual(["a","b"]);
  const json=JSON.parse(conversationDocument(filtered,context,"commndExecution","json"));
  expect(json.context.scope).toEqual({thread:"child",turn:"t"});expect(json.search).toBe("commndExecution");expect(json.items.map((item:any)=>item.id)).toEqual(["a","b"]);
  expect(json.items[1].item.aggregatedOutput).toBe("```\nprivate result");
  const markdown=conversationDocument(filtered,context,"commndExecution","md");
  expect(markdown).toContain("Subagent \u00b7 2026");expect(markdown).not.toContain("\u00c2\u00b7");
  expect(markdown).toContain("## Subagent");expect(markdown).toContain("Inspect commandExecution output");expect(markdown).toContain("````json");expect(markdown).not.toContain("Other answer");
  expect(conversationMatches(items,"   ")).toBe(items);
});

test.each(["opencode_native_terminal_not_observed","opencode_adapter_telemetry_incomplete","invocation_boundary_unverified"])("exports preserve capture warning %s",reason=>{
  const context={run_id:"run",execution_id:"execution",node_id:"node",model:null,native_session:null,scope:{thread:"child"},capture_state:"partial",capture_reason:reason,truncated:true};
  expect(JSON.parse(conversationDocument([],context,"query","json")).context).toEqual(context);
  expect(conversationDocument([],context,"query","md")).toContain(`Capture warning: ${reason}`);
  const telemetry=JSON.parse(telemetryDocument([{name:"span"}],"partial",context,"query"));
  expect(telemetry.context).toEqual(context);expect(telemetry.search).toBe("query");expect(telemetry.records).toEqual([{name:"span"}]);
});

test("exports redact unsafe capture reasons without claiming complete evidence",()=>{
  const context={run_id:"run",execution_id:null,node_id:"node",model:null,native_session:null,scope:{},capture_state:"partial",capture_reason:"https://private.invalid/?api_key=DO_NOT_EXPORT",truncated:true};
  for(const output of [conversationDocument([],context,"","json"),conversationDocument([],context,"","md"),telemetryDocument([],"partial",context,"")]){
    expect(output).not.toContain("DO_NOT_EXPORT");expect(output).not.toContain("private.invalid");expect(output).toContain("unrecognized_error");expect(output).toContain("partial");
  }
});

test("conversation search has clear and empty states, and switching scope resets it",async()=>{
  const first={...run("one","execution"),native_session:"parent"};
  const lane=(id:string,thread:string,text:string)=>({id,thread,started:first.started,ended:first.ended,item:{type:"agentMessage",text}});
  const p={...projection,threads:[{id:"parent",parent:null},{id:"child",parent:"parent",title:"Child reviewer"}],items:[lane("a","parent","Garnet main answer"),lane("b","child","Beryl child answer")]};
  (api.get as jest.Mock).mockImplementation((url:string)=>Promise.resolve({data:url.endsWith("/flow")?{runs:[first]}:{run:first,projection:p,truncated:false}}));
  render(<GraphAgents flowId="flow"/>);
  fireEvent.click(await screen.findByRole("button",{name:/^node-one.*completed$/},{timeout:5000}));
  const search=await screen.findByRole("textbox",{name:"Search conversation"});
  fireEvent.change(search,{target:{value:"Garnet"}});expect(screen.getByText("Garnet main answer")).toBeInTheDocument();
  fireEvent.change(search,{target:{value:"zzzzzzzzzz"}});expect(screen.getByText("No matching messages or tools.")).toBeInTheDocument();expect(screen.getByRole("button",{name:"Export conversation"})).toBeDisabled();
  fireEvent.click(screen.getByRole("button",{name:"Clear",exact:true}));
  expect(search).toHaveValue("");expect(screen.getByText("Garnet main answer")).toBeInTheDocument();
  fireEvent.change(search,{target:{value:"Garnet"}});
  fireEvent.click(screen.getByRole("button",{name:/^Child reviewer.*0 turns/}));
  expect(screen.getByRole("textbox",{name:"Search conversation"})).toHaveValue("");expect(screen.getByText("Beryl child answer")).toBeInTheDocument();expect(screen.queryByText("Garnet main answer")).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:"Export conversation"}));expect(screen.getByRole("button",{name:"Markdown (.md)"})).toBeInTheDocument();expect(screen.getByRole("button",{name:"JSON (.json)"})).toBeInTheDocument();
});

test("recorded names survive canvas rename and older runs use the visible canvas name",async()=>{
  canvasNodes=[{id:"node-one",data:{node:{display_name:"Renamed on canvas"}}},{id:"node-two",data:{node:{display_name:"Follow up"}}}];
  const first={...run("one","execution"),node_label:"Review PR"},second=run("two","execution");
  (api.get as jest.Mock).mockImplementation((url:string)=>Promise.resolve({data:url.endsWith("/flow")?{runs:[first,second]}:{run:url.endsWith("/two")?second:first,projection,truncated:false}}));
  render(<GraphAgents flowId="flow"/>);
  fireEvent.click(await screen.findByRole("button",{name:"Review PR · completed"}));
  await screen.findByRole("heading",{name:"Review PR"});
  expect(screen.getByRole("button",{name:"Follow up · completed"})).toBeInTheDocument();
  expect(screen.queryByRole("button",{name:"Renamed on canvas · completed"})).toBeNull();
  fireEvent.click(screen.getByText("Node identity"));
  expect(screen.getByText("node-one")).toBeInTheDocument();
  expect(screen.getByText("Recorded when this invocation started")).toBeInTheDocument();
  expect(api.get).toHaveBeenCalledWith(expect.stringContaining("/node-one/one"),expect.anything());
});

test("JSON highlighting renders hostile content as text",()=>{
  const {container}=render(<HighlightedJson value={{text:'<img src=x onerror="alert(1)">',count:0}}/>);
  expect(container.querySelector("img")).toBeNull();
  expect(container.querySelectorAll("span").length).toBeGreaterThan(0);
  expect(container.textContent).toContain("<img src=x");
});

test("execution selection separates repeated node invocations and exposes unknown usage",async()=>{
  const first=run("one","execution-one"),second=run("two","execution-two");
  (api.get as jest.Mock).mockImplementation((url:string)=>Promise.resolve({data:url.endsWith("/flow")?{runs:[first,second]}:{run:url.endsWith("/one")?first:second,projection,truncated:false}}));
  render(<GraphAgents flowId="flow"/>);
  const button=await screen.findByRole("button",{name:"node-one · completed"});
  expect(screen.queryByRole("button",{name:"node-two · completed"})).toBeNull();
  fireEvent.click(button);
  await screen.findByRole("heading",{name:"Conversation"});
  expect(screen.getAllByText("Unknown").length).toBeGreaterThan(0);
  fireEvent.change(screen.getByRole("combobox"),{target:{value:"execution-two"}});
  await screen.findByRole("button",{name:"node-two · completed"});
  expect(screen.queryByRole("button",{name:"node-one · completed"})).toBeNull();
  await waitFor(()=>expect(api.get).toHaveBeenCalledWith(expect.stringContaining("/node-two/two"),expect.anything()));
});

test("live summary updates do not restart a slower detail request",async()=>{
  jest.useFakeTimers();
  let view:ReturnType<typeof render>|undefined;
  try {
    let count=0;
    const current={...run("live","execution"),status:"running",ended:null};
    (api.get as jest.Mock).mockImplementation((url:string)=>url.endsWith("/flow")
      ?Promise.resolve({data:{runs:[{...current,event_count:++count}]}})
      :new Promise(resolve=>setTimeout(()=>resolve({data:{run:current,projection,truncated:false}}),5000)));
    view=render(<GraphAgents flowId="flow"/>);
    await act(async()=>{await Promise.resolve()});
    fireEvent.click(screen.getByRole("button",{name:"node-live · running"}));
    for(let index=0;index<5;index++)await act(async()=>{jest.advanceTimersByTime(1000)});
    expect(screen.getByRole("heading",{name:"Conversation"})).toBeInTheDocument();
    expect((api.get as jest.Mock).mock.calls.filter(([url])=>String(url).includes("/node-live/live"))).toHaveLength(1);
  } finally {view?.unmount();jest.clearAllTimers();jest.useRealTimers()}
});


test("conversation follows diagnostics, roles differ and command evidence starts collapsed",async()=>{
 const first=run("one","execution");
 const items=[{id:"user",thread:"one",started:first.started,ended:first.ended,item:{type:"userMessage",text:"Read the file"}},{id:"tool",thread:"one",started:first.started,ended:first.ended,item:{type:"commandExecution",command:"cat README.md",exitCode:0,aggregatedOutput:"output evidence",commandActions:[{type:"read",name:"README.md"}]}},{id:"answer",thread:"one",started:first.started,ended:first.ended,item:{type:"agentMessage",text:"**Done**"}},{id:"child",thread:"child-unique-thread",started:first.started,ended:first.ended,item:{type:"agentMessage",text:"Child answer"}}];
 (api.get as jest.Mock).mockImplementation((url:string)=>Promise.resolve({data:url.endsWith("/flow")?{runs:[first]}:{run:first,projection:{...projection,items},truncated:true}}));
 const {container}=render(<GraphAgents flowId="flow"/>);
 fireEvent.click(await screen.findByRole("button",{name:"node-one · completed"}));
 await screen.findByRole("navigation",{name:"Activity selection"});
 fireEvent.click(screen.getByRole("button",{name:"All activity",exact:true}));
 const conversation=await screen.findByRole("region",{name:"Conversation messages and tools"});
 expect(screen.getByRole("region",{name:"Usage and diagnostics"}).compareDocumentPosition(conversation)&Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
 expect(conversation).toHaveAttribute("tabindex","0");
 expect(container.querySelector('[data-message-role="user"]')).toHaveClass("items-end");
 expect(container.querySelector('[data-message-role="agent"]')).toHaveClass("items-start");
 expect(screen.getByText("Subagent e-thread")).toBeInTheDocument();
 expect(screen.queryByText("Message source")).toBeNull();
 const source=screen.getAllByRole("button",{name:"View message source"})[0];
 fireEvent.click(source);
 const dialog=await screen.findByRole("dialog",{name:"Message source"});
 expect(dialog).toHaveTextContent('"type": "userMessage"');
 fireEvent.click(screen.getByRole("button",{name:"Close message source"}));
 await waitFor(()=>expect(screen.queryByRole("dialog",{name:"Message source"})).toBeNull());
 expect(source).toHaveFocus();
 expect(screen.getByText("Done").tagName).toBe("STRONG");
 expect(screen.getByText("cat README.md")).toBeInTheDocument();
 expect(screen.getByText("Read README.md")).toBeInTheDocument();
 expect(screen.getByText("Native tool metadata").closest("details")).not.toHaveAttribute("open");
 expect(screen.getByText("output evidence").closest("details")).not.toHaveAttribute("open");
 expect(screen.getByRole("alert")).toHaveTextContent("view is partial");
});

test("Markdown formats safely without HTML or remote images",()=>{
 const {container}=render(<MessageMarkdown text={'**Answer** `code` <img src=x onerror="alert(1)">\n![remote](https://external.invalid/x)\n[unsafe](javascript:alert(1))'}/>);
 expect(container.querySelector("strong")).toHaveTextContent("Answer");
 expect(container.querySelector("code")).toHaveTextContent("code");
 expect(container.querySelectorAll("img,script,iframe")).toHaveLength(0);
 expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
 expect(commandTitle({commandActions:[null,{}, {type:"read",name:"file"}]})).toBe("Read file");
 expect(commandTitle({command:"a"})).toBe("Shell command");
 expect(activityTitle({type:"subAgentActivity",kind:"started",agentPath:"/root/read"})).toBe("Subagent started · /root/read");
 expect(activityTitle({type:"subAgentActivity",kind:"completed"})).toBe("Subagent completed");
});


test("node Activity selects the newest execution and invocation of the selected node",async()=>{
  activityTarget={flowId:"flow",nodeId:"node-target"};
  canvasNodes=[{id:"node-target",selected:true,data:{node:{display_name:"Target agent"}}}];
  const old={...run("old","old-execution"),node:"node-target"};
  const other={...run("other","other-execution"),started:"2026-10-16T12:00:00Z"};
  const newest={...run("newest","target-execution"),node:"node-target",started:"2026-10-16T10:00:00Z"};
  const all=[other,old,newest];
  (api.get as jest.Mock).mockImplementation((url:string)=>Promise.resolve({data:url.endsWith("/flow")?{runs:all}:{run:all.find(run=>url.endsWith("/"+run.id)),projection,truncated:false}}));
  render(<GraphAgents flowId="flow"/>);
  await screen.findByRole("heading",{name:"Target agent"});
  expect(screen.getByRole("combobox")).toHaveValue("target-execution");
  fireEvent.change(screen.getByRole("combobox"),{target:{value:"other-execution"}});
  await screen.findByText("No captured activity for the selected node in this graph execution.");
  expect(screen.queryByRole("heading",{name:"Target agent"})).toBeNull();
});


test("opening Agents directly ignores canvas selection without an Activity target",async()=>{
  canvasNodes=[{id:"node-one",selected:true,data:{node:{}}}];
  const first=run("one","execution");
  (api.get as jest.Mock).mockImplementation((url:string)=>Promise.resolve({data:url.endsWith("/flow")?{runs:[first]}:{run:first,projection,truncated:false}}));
  const view=render(<GraphAgents flowId="flow"/>);
  await screen.findByRole("button",{name:/^node-one .* completed$/});
  expect(screen.queryByRole("article",{name:"Selected agent run"})).toBeNull();
  view.unmount();
  expect(clearTarget).toHaveBeenCalled();
});


test("cumulative charts carry forward threads without double-counting observations",()=>{
  const point=(at:string,thread:string,input:number,cost:number|null)=>({at,thread,usage:{inputTokens:input,cachedInputTokens:0,outputTokens:1,reasoningOutputTokens:0},cost:{amount:cost} as any});
  const points=aggregateUsagePoints([
    point("2026-10-23T14:00:03Z","parent",25,.003),
    point("2026-10-23T14:00:01Z","parent",10,.001),
    point("2026-10-23T14:00:02Z","child",5,.002),
  ]);
  expect(points.map(p=>p.usage?.inputTokens)).toEqual([10,15,30]);
  expect(points.map(p=>p.cost)).toEqual([.001,.003,.005]);
  expect(aggregateUsagePoints([point("2026-10-23T14:00:01Z","parent",10,null)])[0].cost).toBeNull();
  expect(aggregateUsagePoints([point("invalid","parent",10,.001)])).toEqual([]);
});

test("all runtime records are listed and fuzzy search can find records beyond fifty",()=>{
  const records=Array.from({length:65},(_,index)=>({name:index===64?"opencode.commandExecution":`session.record.${index}`,signal:"span",attributes:{"conversation.id":"ses_test"},id:index}));
  render(<RuntimeRecords records={records} coverage="Observed adapter records"/>);
  expect(screen.getByText("65 of 65 records")).toBeInTheDocument();
  expect(screen.getByText("65. opencode.commandExecution / span")).toBeInTheDocument();
  fireEvent.change(screen.getByRole("textbox",{name:"Search OpenTelemetry records"}),{target:{value:"commndExecution"}});
  expect(screen.getByText("65. opencode.commandExecution / span")).toBeInTheDocument();
  expect(screen.queryByText("1. session.record.0 / span")).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:"Clear"}));
  expect(screen.getByText("65 of 65 records")).toBeInTheDocument();
});


test("scoped charts retain keyboard access without a second thread selector or repeated readout",()=>{
  const usage={inputTokens:10,cachedInputTokens:0,outputTokens:1,reasoningOutputTokens:0};
  render(<UsageCharts scopeLabel="Conversation" projection={{...projection,usage,cost:{amount:.001},usage_points:[{at:"2026-10-23T14:00:01Z",thread:"parent",usage,cost:{amount:.001}}]} as any}/>);
  expect(screen.getByRole("group",{name:"Conversation totals"})).toHaveTextContent("10");
  expect(screen.queryByRole("combobox",{name:"Chart scope"})).toBeNull();
  expect(screen.queryByRole("slider")).toBeNull();
  expect(screen.queryByText(/Observed at/)).toBeNull();
  const chart=screen.getByRole("figure",{name:"Cumulative token usage chart"});
  fireEvent.focus(chart);fireEvent.keyDown(chart,{key:"Home"});
  expect(screen.getByRole("status")).toHaveTextContent("Input: 10");
});

test("scope uses explicit thread and turn attribution and excludes descendants and unrelated telemetry",()=>{
  const usage={inputTokens:10};const cost={amount:.001};
  const p={...projection,threads:[{id:"parent",parent:null},{id:"child",parent:"parent",title:"Review changes"}],
    usage_by_thread:{parent:usage,child:{inputTokens:4}},cost:{amount:.002,per_thread:{parent:cost,child:{amount:.001}}},
    turns:[{id:"first",thread:"parent",usage:{inputTokens:3},cost:{amount:.0003}}],
    items:[{id:"p1",thread:"parent",turn:"first"},{id:"p2",thread:"parent",turn:"second"},{id:"c1",thread:"child",turn:"childturn"}],
    usage_points:[{thread:"parent",turn:"first",at:"2026-10-23T14:00:01Z",usage,turn_usage:{inputTokens:3},cost,turn_cost:{amount:.0003}}],
    telemetry:[{attributes:{"conversation.id":"parent","call.id":"p1"}},{attributes:{"conversation.id":"parent","turn.id":"second"}},{attributes:{"conversation.id":"child","call.id":"c1"}},{attributes:{}}]} as any;
  const parent=scopedProjection(p,{thread:"parent"});expect(parent.items.map(i=>i.id)).toEqual(["p1","p2"]);expect(parent.usage).toEqual(usage);
  const turn=scopedProjection(p,{thread:"parent",turn:"first"});expect(turn.items.map(i=>i.id)).toEqual(["p1"]);expect(turn.usage).toEqual({inputTokens:3});expect(turn.cost.amount).toBe(.0003);expect(turn.usage_points[0].usage).toEqual({inputTokens:3});expect(turn.telemetry).toHaveLength(1);
  const unknown=scopedProjection({...p,turns:[{id:"first",thread:"parent",usage:null,cost:{amount:null}}]},{thread:"parent",turn:"first"});expect(unknown.usage).toBeNull();expect(unknown.cost.amount).toBeNull();
  expect(scopedProjection(p,{})).toBe(p);
});

test("conversation hierarchy preserves titles, orphans and cycles without inventing links",()=>{
  const rows=conversationRows({...projection,threads:[{id:"parent",parent:null},{id:"child",parent:"parent",title:"Review changes"},{id:"orphan",parent:"missing"},{id:"a",parent:"b"},{id:"b",parent:"a"}]} as any,"parent");
  expect(rows.map(r=>r.id)).toEqual(["parent","child","orphan","a","b"]);
  expect(rows.find(r=>r.id==="child")).toMatchObject({depth:1,title:"Review changes"});
  expect(rows.find(r=>r.id==="orphan")?.depth).toBe(0);
});

test("Gantt scopes messages to child and turn, breadcrumbs restore ancestors and earlier run navigation resets scope",async()=>{
  const first={...run("one","current"),node:"node",native_session:"parent",started:"2026-10-15T10:00:10Z",ended:"2026-10-15T10:00:20Z"};
  const old={...run("old","previous"),node:"node",native_session:"parent"};
  const lane=(id:string,thread:string,turn:string,text:string)=>({id,thread,turn,started:first.started,ended:first.ended,item:{type:"agentMessage",text}});
  const p={...projection,threads:[{id:"parent",parent:null},{id:"child",parent:"parent",title:"Review changes"}],usage_by_thread:{child:{inputTokens:4}},
    turns:[{id:"t1",thread:"parent",started:first.started,ended:first.ended,status:"completed"},{id:"c1",thread:"child",started:first.started,ended:first.ended,status:"completed"},{id:"c2",thread:"child",started:first.started,ended:first.ended,status:"completed"}],
    items:[lane("a","parent","t1","Parent answer"),lane("b","child","c1","First child answer"),lane("c","child","c2","Second child answer")]};
  (api.get as jest.Mock).mockImplementation((url:string)=>Promise.resolve({data:url.endsWith("/flow")?{runs:[first,old]}:{run:url.endsWith("/old")?old:first,projection:p,truncated:false}}));
  render(<GraphAgents flowId="flow"/>);
  fireEvent.click(await screen.findByRole("button",{name:/Review changes.*2 turns.*completed$/,exact:false}));
  expect(await screen.findByText("First child answer")).toBeInTheDocument();expect(screen.queryByText("Parent answer")).toBeNull();
  fireEvent.click(screen.getByRole("button",{name:/^Turn 1.*Review changes.*completed, /}));
  expect(screen.queryByText("Second child answer")).toBeNull();
  expect(screen.getAllByRole("region",{name:"Usage overview"})).toHaveLength(1);
  expect(screen.getAllByRole("region",{name:"OpenTelemetry"})).toHaveLength(1);
  fireEvent.click(screen.getByRole("navigation",{name:"Activity selection"}).querySelector('button')!);
  expect(screen.getByText("Parent answer")).toBeInTheDocument();expect(screen.getByText("Second child answer")).toBeInTheDocument();
  expect(screen.queryByText("Technical details",{selector:"summary"})).toBeNull();
  expect(screen.getAllByRole("region",{name:"Usage overview"})).toHaveLength(1);
  fireEvent.click(screen.getByRole("button",{name:/Earlier run in this conversation/}));
  await waitFor(()=>expect(screen.getByRole("combobox")).toHaveValue("previous"));
  expect(screen.queryByText("This conversation only; excludes subagents")).toBeNull();
});

test("unpriced observations show Unknown instead of an artificial cost axis",()=>{
  render(<UsageCharts projection={{...projection,usage_points:[{at:"2026-10-23T14:00:01Z",thread:"parent",usage:{inputTokens:10},cost:{amount:null}}]} as any}/>);
  expect(screen.getByRole("img",{name:"Estimated cost unavailable"})).toHaveTextContent("Unknown");
  expect(screen.queryByRole("figure",{name:"Cumulative estimated cost chart"})).toBeNull();
});

test("agent rows contain separate turn segments, preserve idle gaps and do not draw an invocation bar",async()=>{
 const first=run("one","execution"),start="2026-10-15T10:00:00Z",end="2026-10-15T10:00:40Z";
 const turn=(id:string,thread:string,a:number,b:number)=>({id,thread,started:`2026-10-15T10:00:${String(a).padStart(2,"0")}Z`,ended:`2026-10-15T10:00:${String(b).padStart(2,"0")}Z`,status:"completed"});
 const p={...projection,threads:[{id:"one",parent:null},{id:"child",parent:"one",title:"Review changes"}],turns:[turn("a","one",10,12),turn("b","one",20,24),turn("c","child",14,16)]};
 (api.get as jest.Mock).mockImplementation((url:string)=>Promise.resolve({data:url.endsWith("/flow")?{runs:[{...first,started:start,ended:end}]}:{run:{...first,started:start,ended:end},projection:p,truncated:false}}));
 render(<GraphAgents flowId="flow"/>);
 await waitFor(()=>expect(screen.getAllByTestId("agent-turn-bar")).toHaveLength(3));
 const rows=screen.getAllByTestId("agent-timeline-row");expect(rows).toHaveLength(2);
 expect(rows[0].querySelectorAll('[data-testid="agent-turn-bar"]')).toHaveLength(2);
 expect(screen.getAllByTestId("agent-turn-bar").map(bar=>bar.style.left)).toEqual(["25%","50%","35%"]);
 expect(screen.getAllByTestId("agent-turn-bar").map(bar=>bar.style.width)).toEqual(["5%","10%","5%"]);
 expect(screen.queryByRole("button",{name:/40.0s/})).toBeNull();
 expect(screen.getByText("40.0 seconds")).toBeInTheDocument();
 expect(screen.getByTestId("agent-timeline-axis")).toHaveAttribute("data-start",String(Date.parse(start)));
 expect(screen.getByTestId("agent-timeline-axis")).toHaveAttribute("data-end",String(Date.parse(end)));
 fireEvent.click(screen.getByRole("button",{name:/^Turn 2.*Main conversation/}));
 expect(screen.getByRole("navigation",{name:"Activity selection"})).toHaveTextContent("Turn 2");
});

test("turn segments are clipped to the unchanged axis and empty intervals stay blank",()=>{
 const lane=(a:string,b:string|null)=>({id:"t",started:a,ended:b});const start=Date.parse("2026-10-15T10:00:00Z"),end=start+40000;
 expect(turnPosition(lane("2026-10-15T10:00:10Z","2026-10-15T10:00:10Z"),start,end)).toBeNull();
 expect(turnPosition(lane("bad",null),start,end)).toBeNull();
 expect(turnPosition(lane("2026-10-15T09:59:59Z","2026-10-15T10:00:02Z"),start,end)).toEqual({left:0,width:5});
});


test("running totals start at zero, then use observed values and preserve unknown cost",()=>{
 const {rerender}=render(<UsageCharts projection={projection as any} running/>);
 const totals=screen.getByRole("group",{name:"Run totals"});
 expect(totals).not.toHaveTextContent("Unknown");
 expect(totals.querySelectorAll(".tabular-nums")).toHaveLength(5);
 expect([...totals.querySelectorAll(".tabular-nums")].map(el=>el.textContent)).toEqual(["0","0","0","0","$0.000000"]);
 expect(screen.queryByText("Aggregate usage is incomplete.")).toBeNull();
 rerender(<UsageCharts running projection={{...projection,usage:{inputTokens:12,outputTokens:3},usage_points:[{at:"2026-10-25T10:00:00Z",thread:"main",usage:{inputTokens:12,outputTokens:3},cost:{amount:null}}]} as any}/>);
 expect(totals).toHaveTextContent("12");expect(totals).toHaveTextContent("3");
 expect([...totals.querySelectorAll(".tabular-nums")].map(el=>el.textContent)).toEqual(["12","Unknown","3","Unknown","Unknown"]);
 rerender(<UsageCharts projection={projection as any}/>);
 expect(totals.querySelectorAll(".tabular-nums")).toHaveLength(5);
 expect([...totals.querySelectorAll(".tabular-nums")].every(el=>el.textContent==="Unknown")).toBe(true);
 expect(screen.getByText("Aggregate usage is incomplete.")).toBeInTheDocument();
});

test("an unpriced usage observation never becomes a zero estimate while running",()=>{
 render(<UsageCharts running projection={{...projection,usage_points:[{at:"2026-10-25T10:00:00Z",thread:"main",usage:{},cost:{amount:null}}]} as any}/>);
 expect(screen.getByRole("group",{name:"Run totals"})).not.toHaveTextContent("$0.000000");
 expect(screen.getByRole("img",{name:"Estimated cost unavailable"})).toHaveTextContent("Unknown");
});


test.each([null,"invocation_boundary_unverified"])("initial graph totals respect capture reason %s",async(reason)=>{
 const active={...run("one","execution"),status:"running",ended:null,reason,native_session:null};
 (api.get as jest.Mock).mockImplementation((url:string)=>Promise.resolve({data:url.endsWith("/flow")?{runs:[active]}:{run:active,projection,truncated:false}}));
 render(<GraphAgents flowId="flow"/>);
 fireEvent.click(await screen.findByRole("button",{name:"node-one · running"}));
 const totals=await screen.findByRole("group",{name:"Run totals"});
 if(reason)expect(totals).toHaveTextContent("Unknown");
 else {expect(totals).not.toHaveTextContent("Unknown");expect(totals).toHaveTextContent("$0.000000")}
});
