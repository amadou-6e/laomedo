import { create } from "zustand";

type ActivityTarget = { flowId:string; nodeId:string };
export const useAgentActivityStore = create<{target:ActivityTarget|null;openActivity:(flowId:string,nodeId:string)=>void;clearTarget:()=>void}>(set=>({
  target:null,
  openActivity:(flowId,nodeId)=>set({target:{flowId,nodeId}}),
  clearTarget:()=>set({target:null}),
}));
