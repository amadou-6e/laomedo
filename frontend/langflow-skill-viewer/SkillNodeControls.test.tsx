import { fireEvent, render, renderHook, screen } from "@testing-library/react";
import RenderInputParameters from "./index";
import { advancedSkillFields, isSkillControlHidden, skillFieldInfo, skillNodeDescription } from "./SkillNodeControls";
import useRowData from "@/modals/editNodeModal/hooks/use-row-data";

const update = jest.fn();
let edges: any[] = [];
const scalar = { show: true, type: "str", advanced: false, value: "" };
const data = { id: "skill", type: "LaomedoSkill", node: { description: "Read an immutable skill or propose a traceable, atomic multi-file revision.", template: {
  source: scalar, skill_id: { ...scalar, value: "real-skill" },
  revision_id: { ...scalar, value: "sha256:saved-pin" },
  commit_id: { ...scalar, value: "saved-parent", advanced: true },
  discovery_status: scalar, edit_request: { ...scalar, value: "saved request" },
  operation: { ...scalar, type: "other" },
} } };
jest.mock("@xyflow/react", () => ({ useUpdateNodeInternals: () => update }));
jest.mock("@/stores/flowStore", () => ({ __esModule: true, default: (select: any) => select({ edges, nodes: [{ id: "skill", data: { type: "LaomedoSkill" } }] }) }));
jest.mock("@/CustomNodes/helpers/get-node-input-colors", () => ({ getNodeInputColors: () => [] }));
jest.mock("@/CustomNodes/helpers/get-node-input-colors-name", () => ({ getNodeInputColorsName: () => [] }));
jest.mock("@/CustomNodes/helpers/sort-tool-mode-field", () => ({ sortToolModeFields: () => 0 }));
jest.mock("@/CustomNodes/utils/get-field-title", () => ({ __esModule: true, default: (_: any, name: string) => name }));
jest.mock("@/CustomNodes/utils/sort-fields", () => ({ __esModule: true, default: () => 0 }));
jest.mock("@/utils/reactflowUtils", () => ({ scapedJSONStringfy: JSON.stringify }));
jest.mock("./utils", () => ({ findPrimaryInput: (fields: string[]) => ({ displayHandleMap: new Map(fields.map(name => [name, name === "operation" || edges.some(e => e.data.targetHandle.fieldName === name)])), primaryInputFieldName: "operation" }) }));
jest.mock("../NodeInputField", () => ({ __esModule: true, default: (props: any) => <input aria-label={props.name} title={props.info} data-handle={String(props.displayHandle)} defaultValue={props.data.node.template[props.name].value || ""} /> }));

function draw(node = data, showNode = true) {
  return render(<RenderInputParameters data={node} types={{}} isToolMode={false} showNode={showNode} shownOutputs={[]} showHiddenOutputs={false} />);
}
beforeEach(() => { edges = []; update.mockClear(); });

test("legacy flags cannot expose Edit Request or leave Revision outside settings; values are retained", () => {
  const saved = JSON.stringify(data);
  draw();
  expect(screen.queryByRole("textbox", { name: "edit_request", hidden: true })).toBeNull();
  expect(screen.queryByRole("textbox", { name: "revision_id" })).toBeNull();
  expect(screen.getByRole("textbox", { name: "operation" })).toHaveAttribute("data-handle", "true");
  const toggle = screen.getByRole("button", { name: "Advanced settings" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(toggle);
  expect(screen.getAllByRole("textbox", { name: "revision_id" })).toHaveLength(1);
  expect(screen.getByRole("textbox", { name: "revision_id" })).toHaveValue("sha256:saved-pin");
  expect(screen.getByRole("textbox", { name: "commit_id" })).toHaveValue("saved-parent");
  fireEvent.change(screen.getByRole("textbox", { name: "revision_id" }), { target: { value: "updated pin" } });
  fireEvent.click(toggle); fireEvent.click(toggle);
  expect(screen.getByRole("textbox", { name: "revision_id" })).toHaveValue("updated pin");
  expect(JSON.stringify(data)).toBe(saved);
});

test("settings dialog excludes a saved visible request using the actual node type", () => {
  const { result } = renderHook(() => useRowData(data.node as any, true, "skill"));
  expect(result.current.map(row => row.key)).not.toContain("edit_request");
  expect(result.current.map(row => row.key)).toContain("revision_id");
  expect(data.node.template.edit_request.value).toBe("saved request");
});

test("connected settings retain their ordinary socket and hidden fields stay hidden", () => {
  edges = [{ target: "skill", data: { targetHandle: { fieldName: "revision_id" } } }];
  draw({ ...data, node: { ...data.node, template: { ...data.node.template, revision_id: { ...data.node.template.revision_id, advanced: true }, commit_id: { ...data.node.template.commit_id, show: false } } } });
  expect(screen.getByRole("textbox", { name: "revision_id" })).toHaveAttribute("data-handle", "true");
  expect(screen.queryByRole("button", { name: "Advanced settings" })).toBeNull();
});

test("minimized node hides settings; unrelated nodes and custom descriptions are preserved", () => {
  draw(data, false);
  expect(screen.queryByRole("button", { name: "Advanced settings" })).toBeNull();
  expect(advancedSkillFields({ ...data, type: "Other" }, Object.keys(data.node.template), [], false)).toEqual([]);
  expect(isSkillControlHidden({ ...data, type: "Other" }, "edit_request")).toBe(false);
  expect(skillNodeDescription(data)).toBe("Use and edit versioned skill files.");
  expect(skillNodeDescription({ ...data, node: { ...data.node, description: "My own explanation" } })).toBe("My own explanation");
  expect(skillFieldInfo(data, "discovery_status")).toMatch(/never runs a Skill/);
  expect(skillFieldInfo(data, "source")).toMatch(/host source service/);
});
