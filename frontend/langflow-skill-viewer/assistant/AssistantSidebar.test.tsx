import { MemoryRouter } from "react-router-dom";
import { useState } from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import AssistantSidebar from "./AssistantSidebar";
import { useAssistantSidebarStore } from "./sidebarStore";

jest.mock("@/stores/authStore", () => ({ __esModule: true, default: (select: any) => select({ userData: { id: "owner" } }) }));
jest.mock("./AssistantPage", () => ({ __esModule: true, default: ({ onSelectConversation, headerActions }: any) => {
  const [draft, setDraft] = useState("");
  return <div>{headerActions}<input aria-label="Draft" value={draft} onChange={(event) => setDraft(event.target.value)} /><button onClick={() => onSelectConversation({ conversation: "saved-chat" })}>Select saved chat</button></div>;
} }));

beforeEach(() => {
  useAssistantSidebarStore.setState({ open: false });
  global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
});

test("opening is lazy and close/reopen preserves the mounted draft and saved conversation link", () => {
  render(<MemoryRouter><AssistantSidebar /></MemoryRouter>);
  expect(screen.queryByRole("textbox")).toBeNull();
  // The real header uses this same store action; opening does not submit chat.
  act(() => useAssistantSidebarStore.getState().setOpen(true));
  fireEvent.change(screen.getByRole("textbox", { name: "Draft" }), { target: { value: "Unsent work" } });
  fireEvent.click(screen.getByRole("button", { name: "Select saved chat" }));
  expect(screen.getByRole("link", { name: "Open full-window assistant" })).toHaveAttribute("href", "/assistant?conversation=saved-chat");
  fireEvent.click(screen.getByRole("button", { name: "Collapse assistant sidebar" }));
  expect(screen.queryByRole("textbox")).toBeNull();
  act(() => useAssistantSidebarStore.getState().setOpen(true));
  expect(screen.getByRole("textbox", { name: "Draft" })).toHaveValue("Unsent work");
  expect(screen.getByRole("link", { name: "Open full-window assistant" })).toHaveAttribute("href", "/assistant?conversation=saved-chat");
});

test("keyboard resizing is bounded and exposes the current width", () => {
  useAssistantSidebarStore.setState({ open: true });
  render(<MemoryRouter><AssistantSidebar /></MemoryRouter>);
  const divider = screen.getByRole("separator", { name: "Resize assistant" });
  expect(divider).toContainElement(screen.getByRole("button", { name: "Collapse assistant sidebar" }));
  fireEvent.keyDown(divider, { key: "Home" });
  expect(divider).toHaveAttribute("aria-valuenow", "280");
  fireEvent.keyDown(divider, { key: "ArrowRight" });
  expect(divider).toHaveAttribute("aria-valuenow", "280");
  fireEvent.keyDown(divider, { key: "End" });
  expect(divider.getAttribute("aria-valuenow")).toBe(divider.getAttribute("aria-valuemax"));
});


test.each([true,false])("close avoids a hidden rail opener (%s)",hidden=>{
 useAssistantSidebarStore.setState({open:true});
 const focus=jest.fn();
 const frame=jest.spyOn(window,"requestAnimationFrame").mockImplementation(callback=>{callback(0);return 1;});
 const wrapper=document.createElement("div");
 if(hidden)wrapper.setAttribute("aria-hidden","true");
 const opener=document.createElement("button");opener.id="laomedo-assistant-opener";opener.focus=focus;
 wrapper.appendChild(opener);document.body.appendChild(wrapper);
 try {
  render(<MemoryRouter><AssistantSidebar/></MemoryRouter>);
  fireEvent.click(screen.getByRole("button",{name:"Collapse assistant sidebar"}));
  expect(focus).toHaveBeenCalledTimes(hidden?0:1);
 } finally {wrapper.remove();frame.mockRestore();}
});
