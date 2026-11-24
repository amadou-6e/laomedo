import React from "react";
import {render,screen,waitFor,fireEvent} from "@testing-library/react";
import {AgentActivityModal} from "./index";
import {api} from "@/controllers/API/api";
jest.mock("@/controllers/API/api",()=>({api:{get:jest.fn()}}));
jest.mock("@/customization/utils/urls",()=>({getBaseUrl:()=>"/api/v1/"}));
jest.mock("@/pages/FlowPage/components/nodeToolbarComponent/components/toolbar-button",()=>({ToolbarButton:()=>null}));
jest.mock("@/modals/baseModal",()=>{
 const Modal=({children}:any)=><div role="dialog">{children}</div>;
 Modal.Header=({children}:any)=><header>{children}</header>;
 Modal.Content=({children}:any)=><main>{children}</main>;
 return {__esModule:true,default:Modal};
});
const run={id:"one",started:"now",ended:null,status:"failed",stream_state:"partial",provider:"codex-cli",native_session:null,usage:null,event_count:2,reason:"agent_failed"};
const snapshot={schema_version:"laomedo.agent-activity.v1",run,events:[{sequence:1,received_at:"now",kind:"item.completed",raw:{text:"<img src=x onerror=alert(1)>"}}],has_more:true,next_after:1};
const view=()=>render(<AgentActivityModal flowId="flow" nodeId="agent" open setOpen={jest.fn()}/>);
beforeEach(()=>jest.clearAllMocks());
test("shows retained partial native events as text, unknown usage, and read-only pagination",async()=>{
 (api.get as jest.Mock).mockImplementation((url:string)=>Promise.resolve({data:url.endsWith("/agent")?{schema_version:snapshot.schema_version,runs:[run]}:snapshot}));
 const {container}=view();
 await screen.findByTestId("agent-activity-content");
 expect(screen.getByText("partial (agent_failed)")).toBeInTheDocument();
 expect(screen.getAllByText("Unknown")).toHaveLength(2);
 expect(container.querySelector("img")).toBeNull();
 fireEvent.click(screen.getByText("Next events"));
 await waitFor(()=>expect(api.get).toHaveBeenCalledWith(expect.stringContaining("?after=1"),expect.anything()));
});
test("empty history does not fabricate a successful run",async()=>{
 (api.get as jest.Mock).mockResolvedValue({data:{schema_version:snapshot.schema_version,runs:[]}});
 view();await screen.findByText(/No retained activity/);
 expect(screen.queryByTestId("agent-activity-content")).toBeNull();
});
test("failed inspection gives an explicit error",async()=>{
 (api.get as jest.Mock).mockRejectedValue(Error("denied"));
 view();expect(await screen.findByRole("alert")).toHaveTextContent("Activity unavailable");
});
