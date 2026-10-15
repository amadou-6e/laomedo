import { render, screen, fireEvent, waitFor, act } from "@testing-library/react";
import GraphAgents, { HighlightedJson } from "./index";
import { api } from "@/controllers/API/api";
jest.mock("@/controllers/API/api",()=>({api:{get:jest.fn()}}));
jest.mock("@/customization/utils/urls",()=>({getBaseUrl:()=>"/api/v1/"}));
const run=(id:string,execution:string)=>({id,node:`node-${id}`,execution,started:"2026-10-15T10:00:00Z",ended:"2026-10-15T10:00:02Z",status:"completed",stream_state:"complete",event_count:2,native_session:id,model:"gpt-6-luna"});
const projection={turns:[],items:[],threads:[],usage:null,usage_points:[],cost:{amount:null},cost_reason:"Unknown model",telemetry:[],telemetry_coverage:"not observed"};
beforeEach(()=>jest.clearAllMocks());

test("JSON highlighting renders hostile content as text",()=>{
  const {container}=render(<HighlightedJson value={{text:'<img src=x onerror="alert(1)">',count:0}}/>);
  expect(container.querySelector("img")).toBeNull();
  expect(container.querySelectorAll("span").length).toBeGreaterThan(1);
  expect(container.textContent).toContain("<img src=x");
});

test("execution selection separates repeated node invocations and exposes unknown usage",async()=>{
  const first=run("one","execution-one"),second=run("two","execution-two");
  (api.get as jest.Mock).mockImplementation((url:string)=>Promise.resolve({data:url.endsWith("/flow")?{runs:[first,second]}:{run:url.endsWith("/one")?first:second,projection,truncated:false}}));
  render(<GraphAgents flowId="flow"/>);
  const button=await screen.findByRole("button",{name:"node-one · completed"});
  expect(screen.queryByRole("button",{name:"node-two · completed"})).toBeNull();
  fireEvent.click(button);
  await screen.findByRole("heading",{name:"Messages and tools"});
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
    expect(screen.getByRole("heading",{name:"Messages and tools"})).toBeInTheDocument();
    expect((api.get as jest.Mock).mock.calls.filter(([url])=>String(url).includes("/node-live/live"))).toHaveLength(1);
  } finally {view?.unmount();jest.clearAllTimers();jest.useRealTimers()}
});
