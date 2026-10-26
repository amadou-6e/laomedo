import { act, fireEvent, render, screen } from "@testing-library/react";
import useAlertStore from "@/stores/alertStore";
import ErrorAlert from "@/alerts/error";
let mockFlow: any = {nodes:[{data:{type:"LaomedoCodexAgent"}}], buildInfo:null};
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
