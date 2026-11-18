import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import AssistantEntry from "./AssistantEntry";
import AssistantSidebarToggle from "./AssistantSidebarToggle";
import { useAssistantSidebarStore } from "./sidebarStore";
jest.mock("@/stores/authStore",()=>({__esModule:true,default:(select:any)=>select({userData:null})}));
jest.mock("@/components/common/genericIconComponent",()=>({__esModule:true,default:()=> <svg/>}));
jest.mock("./api",()=>({assistantRequest:jest.fn()}));

beforeEach(()=>useAssistantSidebarStore.setState({open:false}));

test.each(["/all","/flow/example"])("header opens full-window chat from %s",path=>{
  render(<MemoryRouter initialEntries={[path]}><AssistantEntry/></MemoryRouter>);
  const link=screen.getByRole("link",{name:"Open full-window assistant"});
  expect(link).toHaveAttribute("href","/assistant");
  expect(link).not.toHaveAttribute("target");
  fireEvent.click(link);
  expect(useAssistantSidebarStore.getState().open).toBe(false);
});

test("rail toggle opens the sidebar and follows the rail's hidden focus state",()=>{
 const {rerender}=render(<ul><AssistantSidebarToggle/></ul>);
 fireEvent.click(screen.getByRole("button",{name:"Open assistant sidebar"}));
 expect(screen.getByRole("button",{name:"Close assistant sidebar"})).toHaveAttribute("aria-expanded","true");
 expect(useAssistantSidebarStore.getState().open).toBe(true);
 rerender(<ul><AssistantSidebarToggle hiddenFromTabOrder/></ul>);
 expect(screen.getByRole("button")).toHaveAttribute("tabindex","-1");
 fireEvent.click(screen.getByRole("button"));
 expect(useAssistantSidebarStore.getState().open).toBe(false);
});
