import { render, screen, fireEvent } from "@testing-library/react";
import AgentAdvancedControls, { advancedAgentFields } from "./AgentAdvancedControls";
const update = jest.fn();
jest.mock("@xyflow/react", () => ({ useUpdateNodeInternals: () => update }));
const field = { show: true, type: "str", advanced: true };
const data = { id: "agent", type: "LaomedoCodexAgent", node: { template: {
  model: field, runner_url: field, request_id: field, skill_reference: { ...field, type: "other" },
  bridge_url: { ...field, show: false }, timeout_seconds: { ...field, advanced: false },
} } };
test("only Agent scalar controls are grouped; hidden and connected fields stay out", () => {
  const fields = Object.keys(data.node.template);
  expect(advancedAgentFields(data, fields, [], false)).toEqual(["runner_url"]);
  expect(advancedAgentFields(data, fields, [{ target: "agent", data: { targetHandle: { fieldName: "runner_url" } } }], false)).toEqual([]);
  expect(advancedAgentFields({ ...data, type: "Other" }, fields, [], false)).toEqual([]);
  expect(advancedAgentFields({ ...data, type: "LaomedoOpenCodeAgent" }, fields, [], false)).toEqual(["runner_url"]);
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

// Exercise the actual grouping renderer; only the individual field widgets are
// replaced here. Real widget/store behavior is checked in the browser.
import RenderInputParameters from "./index";
jest.mock("@/stores/flowStore", () => ({ __esModule: true, default: (select: any) => select({ edges: [] }) }));
jest.mock("@/CustomNodes/helpers/get-node-input-colors", () => ({ getNodeInputColors: () => [] }));
jest.mock("@/CustomNodes/helpers/get-node-input-colors-name", () => ({ getNodeInputColorsName: () => [] }));
jest.mock("@/CustomNodes/helpers/sort-tool-mode-field", () => ({ sortToolModeFields: () => 0 }));
jest.mock("@/CustomNodes/utils/get-field-title", () => ({ __esModule: true, default: (_: any, name: string) => name }));
jest.mock("@/utils/reactflowUtils", () => ({ scapedJSONStringfy: JSON.stringify }));
jest.mock("./utils", () => ({ findPrimaryInput: (fields: string[]) => ({ displayHandleMap: new Map(fields.map(name => [name, name === "skill_reference"])), primaryInputFieldName: "skill_reference" }) }));
jest.mock("../NodeInputField", () => ({ __esModule: true, default: (props: any) => <input aria-label={props.name} data-handle={String(props.displayHandle)} defaultValue={props.data.node.template[props.name].value || ""} /> }));
test("renderer puts each field in exactly one group and preserves ordinary ports", () => {
 const normal = { ...data, node: { template: { ...data.node.template, model: { ...field, advanced: false }, skill_reference: { ...field, type: "other", advanced: false } } } };
 render(<RenderInputParameters data={normal} types={{}} isToolMode={false} showNode shownOutputs={[]} showHiddenOutputs={false} />);
 expect(screen.getByRole("textbox", { name: "model" })).toBeVisible();
 expect(screen.getByRole("textbox", { name: "skill_reference" })).toHaveAttribute("data-handle", "true");
 expect(screen.queryByRole("textbox", { name: "runner_url" })).toBeNull();
 fireEvent.click(screen.getByRole("button", { name: "Advanced controls" }));
 expect(screen.getAllByRole("textbox", { name: "runner_url" })).toHaveLength(1);
 expect(screen.getByRole("textbox", { name: "runner_url" })).toHaveAttribute("data-handle", "false");
 expect(screen.queryByRole("textbox", { name: "bridge_url" })).toBeNull();
 expect(screen.queryByRole("textbox", { name: "request_id" })).toBeNull();
});
test("non-Agent renderer retains upstream advanced visibility", () => {
 render(<RenderInputParameters data={{ ...data, type: "Other" }} types={{}} isToolMode={false} showNode shownOutputs={[]} showHiddenOutputs={false} />);
 expect(screen.queryByRole("button", { name: "Advanced controls" })).toBeNull();
 expect(screen.queryByRole("textbox", { name: "runner_url" })).toBeNull();
});
