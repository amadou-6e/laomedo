import { mutateTemplate } from "./mutate-template";
import type { APIClassType } from "@/types/api";
let mockTemplate: any;
let mockNodeId = 'agent-selection';
let mockCounter = 0;
let mockType = "LaomedoClaudeAgent";
jest.mock("@/stores/flowStore", () => ({__esModule:true,default:{getState:()=>({nodes:[{id:mockNodeId,data:{type:mockType,node:{template:mockTemplate}}}]})}}));
jest.mock("@/modals/issueViewerModal",()=>({nodeKind:(value:string)=>value}));
jest.mock("../../i18n",()=>({__esModule:true,default:{t:(value:string)=>value}}));
jest.mock("./update-hidden-outputs",()=>({updateHiddenOutputs:(_:unknown,value:unknown)=>value}));
const template=(model='fable',effort='low')=>({code:{value:'source'},model:{value:model},runner_url:{value:'http://localhost:8769'},effort:{value:effort,options:['low','max']}});
async function deferredRequest(requested:any,incoming:any,edit:()=>void,field='model',value=requested.model.value){
 let finish!: (value:any)=>void;
 const mutateAsync=jest.fn(()=>new Promise(resolve=>{finish=resolve}));
 const apply=jest.fn(),error=jest.fn();
 await mutateTemplate(value,mockNodeId,{template:requested,outputs:[]} as unknown as APIClassType,apply,{mutateAsync} as never,error,field);
 await jest.advanceTimersByTimeAsync(1000);
 edit();finish({template:incoming,outputs:[]});await jest.advanceTimersByTimeAsync(0);
 expect(error).not.toHaveBeenCalled();return apply;
}
beforeEach(()=>{jest.useFakeTimers();mockNodeId='agent-selection-'+ ++mockCounter;mockType='LaomedoClaudeAgent';mockTemplate=template()});
afterEach(()=>jest.useRealTimers());
test.each(['LaomedoClaudeAgent','LaomedoCodexAgent','LaomedoOpenCodeAgent'])('%s discards previous-model results after a later selection',async type=>{
 mockType=type;const apply=await deferredRequest(template(),template(),()=>{mockTemplate=template('haiku','max')});
 expect(apply).not.toHaveBeenCalled();
});
test('runner change invalidates in-flight model discovery',async()=>{
 const apply=await deferredRequest(template(),template(),()=>{mockTemplate={...template(),runner_url:{value:'http://localhost:9999'}}});
 expect(apply).not.toHaveBeenCalled();
});
test('new model normalizes an effort that cannot exist in its native options',async()=>{
 const requested=template('haiku','max');mockTemplate=requested;
 const incoming={...template('haiku','default'),effort:{value:'default',options:['default']}};
 const apply=await deferredRequest(requested,incoming,()=>{});
 expect(apply).toHaveBeenCalledWith(expect.objectContaining({template:expect.objectContaining({effort:expect.objectContaining({value:'default',options:['default']})})}));
});
test('a valid effort edited during discovery is preserved',async()=>{
 mockTemplate=template();const apply=await deferredRequest(template(),template(),()=>{mockTemplate=template('fable','max')});
 expect(apply).toHaveBeenCalledWith(expect.objectContaining({template:expect.objectContaining({effort:expect.objectContaining({value:'max'})})}));
});
test('ordinary components retain their existing field preservation',async()=>{
 mockType='OtherComponent';const requested=template('haiku','low');mockTemplate=requested;
 const apply=await deferredRequest(requested,{...template('haiku','default'),effort:{value:'default',options:['default']}},()=>{mockTemplate=template('haiku','max')});
 expect(apply).toHaveBeenCalledWith(expect.objectContaining({template:expect.objectContaining({effort:expect.objectContaining({value:'max'})})}));
});


test("explicit refresh awaits the response and only announces applied nonempty models", async()=>{
 let finish!: (value:any)=>void;
 const mutateAsync=jest.fn(()=>new Promise(resolve=>{finish=resolve}));
 const apply=jest.fn(), error=jest.fn(), loaded=jest.fn();
 window.addEventListener("laomedo-model-catalog-loaded",loaded);
 let settled=false;
 const pending=mutateTemplate('fable',mockNodeId,{template:mockTemplate,outputs:[]} as any,apply,{mutateAsync} as never,error,undefined,undefined,undefined,true).then(()=>{settled=true});
 await jest.advanceTimersByTimeAsync(2500);
 expect(settled).toBe(false);expect(loaded).not.toHaveBeenCalled();
 finish({template:{...mockTemplate,model:{value:'fable',options:['fable']}},outputs:[]});
 await pending;
 expect(apply).toHaveBeenCalledTimes(1);expect(loaded).toHaveBeenCalledTimes(1);
 window.removeEventListener("laomedo-model-catalog-loaded",loaded);
});
