import { act, fireEvent, render, screen } from "@testing-library/react";
import useAlertStore from "@/stores/alertStore";
import ErrorAlert from "@/alerts/error";
import { api } from "@/controllers/API/api";
let mockFlow: any = {nodes:[{data:{type:"LaomedoCodexAgent"}}], buildInfo:null};
jest.mock("@/modals/issueViewerModal",()=>({nodeKind:jest.fn()}));
jest.mock("@/i18n",()=>({__esModule:true,default:{t:(key:string)=>key}}));
jest.mock("@/stores/flowStore",()=>({__esModule:true,default:{getState:()=>mockFlow}}));
jest.mock("@/utils/reactflowUtils",()=>({customStringify:JSON.stringify}));
jest.mock("@/components/ui/button",()=>({Button:({size,...props}:any)=><button {...props}/>}));
jest.mock("@/controllers/API/api",()=>({api:{get:jest.fn(),post:jest.fn()}}));
jest.mock("@/customization/utils/urls",()=>({getBaseUrl:()=>"/api/v1/"}));
beforeEach(()=>{useAlertStore.setState({notificationList:[],tempNotificationList:[]});mockFlow={nodes:[{data:{type:"LaomedoCodexAgent"}}],buildInfo:null};});
test("the exact flow failure is retained safely in history without a duplicate toast",()=>{
 mockFlow.buildInfo={error:["prior_run_required"]};
 act(()=>useAlertStore.getState().setErrorData({title:"Failed",list:["prior_run_required"]}));
 expect(useAlertStore.getState().tempNotificationList).toHaveLength(0);
 const item=useAlertStore.getState().notificationList[0];
 expect(item.failure?.diagnostics.code).toBe("prior_run_required");
});

test("model discovery errors retain their code and offer real managed recovery",async()=>{
 (api.get as jest.Mock).mockResolvedValue({data:{state:"offline",can_start:true,reason:"runner_local_offline"}});
 act(()=>useAlertStore.getState().setErrorData({title:"Failed",list:["runner_model_catalog_unavailable_check_runner_connection"]}));
 const item=useAlertStore.getState().tempNotificationList[0];
 render(<ErrorAlert {...item} removeAlert={()=>{}}/>);
 await screen.findByRole("button",{name:"Start local runner"});
 expect(item.failure?.diagnostics.code).toBe("runner_model_catalog_unavailable_check_runner_connection");
 expect(document.body.textContent).not.toContain("previous run's outcome is unconfirmed");
 expect(api.post).not.toHaveBeenCalled();
});
test("an independent error still produces a persistent copyable card",()=>{
 mockFlow.buildInfo={error:["prior_run_required"]};
 act(()=>useAlertStore.getState().setErrorData({title:"Failed",list:["invalid_skill_reference; bearer secret-payload"]}));
 const item=useAlertStore.getState().tempNotificationList[0],dismiss=jest.fn();
 render(<ErrorAlert {...item} removeAlert={dismiss}/>);
 expect(screen.getByRole("button",{name:"Copy error"})).toBeEnabled();
 expect(document.body.textContent).not.toContain("secret-payload");
 fireEvent.click(screen.getByRole("button",{name:"Dismiss"}));expect(dismiss).toHaveBeenCalledWith(item.id);
});

test("native application errors retain every message without Agent advice",async()=>{
 mockFlow={nodes:[],buildInfo:null};
 act(()=>useAlertStore.getState().setErrorData({title:"Flow save failed",list:["Choose a folder.","The flow name is already in use."]}));
 const item=useAlertStore.getState().tempNotificationList[0];
 const writeText=jest.fn().mockResolvedValue(undefined);Object.defineProperty(navigator,"clipboard",{configurable:true,value:{writeText}});
 render(<ErrorAlert {...item} removeAlert={()=>{}}/>);
 expect(screen.getByRole("heading",{name:"Flow save failed"})).toBeVisible();
 expect(screen.getByText("Choose a folder.")).toBeVisible();expect(screen.getByText("The flow name is already in use.")).toBeVisible();
 expect(document.body.textContent).not.toMatch(/runner|existing run|unrecognized_error/);
 fireEvent.click(screen.getByRole("button",{name:"Copy error"}));await screen.findByText("Copied");
 expect(writeText.mock.calls[0][0]).toContain("Choose a folder.");expect(writeText.mock.calls[0][0]).toContain("The flow name is already in use.");
});


test("Skill config cleanup uncertainty uses the shared catalogue without a retry action", async () => {
 const {mutateTemplate}=require("@/CustomNodes/helpers/mutate-template");
 const node={template:{source:{value:"https://example.invalid/owned.git"}},outputs:[],tool_mode:false};
 mockFlow={nodes:[{id:"skill-config-cleanup",data:{type:"LaomedoSkill",node}}],buildInfo:null};
 const mutateAsync=jest.fn().mockRejectedValue({response:{status:400,data:{detail:"repository_cleanup_unverified"}}});
 const setNodeClass=jest.fn(),callback=jest.fn();
 const consoleError=jest.spyOn(console,"error").mockImplementation(()=>{});
 try {
  await act(async()=>{await mutateTemplate(node.template.source.value,"skill-config-cleanup",node,setNodeClass,{mutateAsync},useAlertStore.getState().setErrorData,"source",callback,false,true);});
  expect(mutateAsync).toHaveBeenCalledTimes(1);expect(setNodeClass).not.toHaveBeenCalled();expect(callback).not.toHaveBeenCalled();
  const item=useAlertStore.getState().tempNotificationList[0],dismiss=jest.fn();
  expect(item.failure?.diagnostics.code).toBe("repository_cleanup_unverified");
  render(<ErrorAlert {...item} removeAlert={dismiss}/>);
  expect(screen.getByRole("heading",{name:"Repository cleanup could not be confirmed"})).toBeVisible();
  expect(screen.getByText(/Do not repeat the operation or remove retained clone staging/)).toBeVisible();
  expect(screen.queryByRole("button",{name:/^(Retry|Refresh|Reload files|Restart local backend|Start local runner)$/})).not.toBeInTheDocument();
  fireEvent.click(screen.getByText("Technical details"));expect(screen.getByText(/"code": "repository_cleanup_unverified"/)).toBeVisible();
  const writeText=jest.fn().mockResolvedValue(undefined);Object.defineProperty(navigator,"clipboard",{configurable:true,value:{writeText}});
  fireEvent.click(screen.getByRole("button",{name:"Copy error"}));await screen.findByRole("button",{name:"Copied"});
  expect(writeText.mock.calls[0][0]).toContain('"code": "repository_cleanup_unverified"');
  expect(writeText.mock.calls[0][0]).not.toContain("example.invalid");
  fireEvent.click(screen.getByRole("button",{name:"Dismiss"}));expect(dismiss).toHaveBeenCalledWith(item.id);
 } finally { consoleError.mockRestore(); }
});
