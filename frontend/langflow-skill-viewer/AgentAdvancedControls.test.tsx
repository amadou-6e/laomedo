import { render, screen, fireEvent } from "@testing-library/react";
import AgentAdvancedControls, { advancedAgentFields } from "./AgentAdvancedControls";
const update = jest.fn();
jest.mock("@xyflow/react", () => ({ useUpdateNodeInternals: () => update }));
const field = { show: true, type: "str", advanced: true };
const data = { id: "agent", type: "LaomedoCodexAgent", node: { template: {
  model: field, runner_url: field, request_id: field, skill_reference: { ...field, type: "other" },
  bridge_url: { ...field, show: false },
} } };
test("only Agent scalar controls are grouped; hidden and connected fields stay out", () => {
  const fields = Object.keys(data.node.template);
  expect(advancedAgentFields(data, fields, [], false)).toEqual(["runner_url", "request_id"]);
  expect(advancedAgentFields(data, fields, [{ target: "agent", data: { targetHandle: { fieldName: "runner_url" } } }], false)).toEqual(["request_id"]);
  expect(advancedAgentFields({ ...data, type: "Other" }, fields, [], false)).toEqual([]);
  expect(advancedAgentFields({ ...data, type: "LaomedoOpenCodeAgent" }, fields, [], false)).toEqual(["runner_url", "request_id"]);
});
test("starts collapsed and retains edited values through collapse and reopen", () => {
  render(<AgentAdvancedControls nodeId="a" visible><input aria-label="Runner URL" defaultValue="local" /></AgentAdvancedControls>);
  const toggle = screen.getByRole("button", { name: "Advanced controls" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  expect(screen.queryByRole("textbox")).toBeNull();
  fireEvent.click(toggle);
  fireEvent.change(screen.getByRole("textbox"), { target: { value: "changed" } });
  fireEvent.click(toggle); fireEvent.click(toggle);
  expect(screen.getByRole("textbox")).toHaveValue("changed");
  expect(document.getElementById(toggle.getAttribute("aria-controls")!)).toBeVisible();
});
test("the minimized node hides the entire disclosure", () => {
  render(<AgentAdvancedControls nodeId="a" visible={false}>Controls</AgentAdvancedControls>);
  expect(screen.queryByRole("button")).toBeNull();
});
