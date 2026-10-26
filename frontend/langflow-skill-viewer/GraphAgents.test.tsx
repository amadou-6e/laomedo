import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import GraphAgents, { HighlightedJson, MessageMarkdown, commandTitle, activityTitle } from "./index";
import { api } from "@/controllers/API/api";
jest.mock("react-syntax-highlighter",()=>({Prism:({children}:{children:string})=><pre><span>{children}</span></pre>}));
jest.mock("@/controllers/API/api",()=>({api:{get:jest.fn(),post:jest.fn()}}));
jest.mock("@/customization/utils/urls",()=>({getBaseUrl:()=>"/api/v1/"}));
let canvasNodes:unknown[]=[];
let activityTarget:{flowId:string;nodeId:string}|null=null;
const clearTarget=jest.fn(()=>{activityTarget=null});
jest.mock("@/stores/agentActivityStore",()=>({useAgentActivityStore:Object.assign((select:any)=>select({target:activityTarget}),{getState:()=>({clearTarget})})}));
jest.mock("@/stores/flowStore",()=>({__esModule:true,default:(select:(state:unknown)=>unknown)=>select({nodes:canvasNodes})}));
const run=(id:string,execution:string)=>({id,node:`node-${id}`,execution,started:"2026-10-15T10:00:00Z",ended:"2026-10-15T10:00:02Z",status:"completed",stream_state:"complete",event_count:2,native_session:id,model:"gpt-6-luna"});
const projection={turns:[],items:[],threads:[],usage:null,usage_points:[],cost:{amount:null},cost_reason:"Unknown model",telemetry:[],telemetry_coverage:"not observed"};
jest.unmock("react-markdown");
jest.mock("@/components/ui/button",()=>({Button:jest.requireActual("react").forwardRef(({variant,size,...props}:any,ref:any)=><button ref={ref} {...props}/>)}));
jest.mock("@/components/ui/popover",()=>{const primitive=jest.requireActual("@radix-ui/react-popover");return {Popover:primitive.Root,PopoverTrigger:primitive.Trigger,PopoverContent:primitive.Content};});
jest.mock("@/components/ui/badge",()=>({Badge:({variant,size,...props}:any)=><span {...props}/>}));
// Keep this suite focused on activity behavior; the real code viewer is checked in-browser.
jest.mock("@/components/common/genericIconComponent",()=>({__esModule:true,default:()=> <svg/>}));
jest.mock("@/components/core/codeTabsComponent",()=>({__esModule:true,default:({code}:{code:string})=> <pre><span>{code}</span></pre>}));
beforeEach(()=>{jest.clearAllMocks();canvasNodes=[];activityTarget=null});

test("recorded names survive canvas rename and older runs use the visible canvas name",async()=>{
  canvasNodes=[{id:"node-one",data:{node:{display_name:"Renamed on canvas"}}},{id:"node-two",data:{node:{display_name:"Follow up"}}}];
  const first={...run("one","execution"),node_label:"Review PR"},second=run("two","execution");
  (api.get as jest.Mock).mockImplementation((url:string)=>Promise.resolve({data:url.endsWith("/flow")?{runs:[first,second]}:{run:first,projection,truncated:false}}));
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

test("Claude messages use their recorded provider instead of the Codex label",async()=>{
  const first={...run("one","execution"),provider:"claude-code"};
  const item={id:"message",thread:"one",turn:"turn",started:first.started,ended:first.ended,item:{type:"agentMessage",text:"A real provider label belongs here."}};
  (api.get as jest.Mock).mockImplementation((url:string)=>Promise.resolve({data:url.endsWith("/flow")?{runs:[first]}:{run:first,projection:{...projection,items:[item]},truncated:false}}));
  render(<GraphAgents flowId="flow"/>);
  fireEvent.click(await screen.findByRole("button",{name:"node-one \u00b7 completed"}));
  await screen.findByText("Claude",{exact:true});
  expect(screen.queryByText("Codex",{exact:true})).toBeNull();
});

test("Claude terminal diagnostics remain separate from complete execution evidence",async()=>{
  const first={...run("one","execution"),provider:"claude-code",model:null};
  const diagnostics=[{evidence:"terminal_receipt_only",tools_enabled:false,reported_session_cost_usd:0.01,cost_basis:"CLI estimate; cumulative session, not a subscription charge"}];
  (api.get as jest.Mock).mockImplementation((url:string)=>Promise.resolve({data:url.endsWith("/flow")?{runs:[first]}:{run:first,projection:{...projection,diagnostics},truncated:false}}));
  render(<GraphAgents flowId="flow"/>);
  fireEvent.click(await screen.findByRole("button",{name:"node-one \u00b7 completed"}));
  await screen.findByText(/Feed completion does not establish complete execution evidence/);
  fireEvent.click(screen.getByText("Claude terminal receipt 1"));
  expect(await screen.findByText(/terminal_receipt_only/)).toBeInTheDocument();
  expect(screen.getByText(/Model unconfirmed/)).toBeInTheDocument();
});
