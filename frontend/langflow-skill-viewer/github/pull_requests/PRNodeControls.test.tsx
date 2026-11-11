import { render, screen } from "@testing-library/react";
import RenderInputParameters from "./index";
import { isPRNode, prChoicePlaceholder, prFieldTemplate, PR_DISCOVERY_ERROR } from "./PRNodeControls";

const scalar = { show: true, type: "str", advanced: false, value: "" };
const node = (status = PR_DISCOVERY_ERROR) => ({ id: "pr", type: "LaomedoGitHubPR", node: { template: {
  repository_url: { ...scalar, value: "https://github.com/owner/repo" },
  labels: { ...scalar, value: ["backend"], options: ["backend"] },
  pr_choice: { ...scalar, value: "#42 Saved title", options: ["#42 Saved title"] },
  state: { ...scalar, advanced: true, value: "closed", options: ["open", "closed", "all"] },
  pr_context: { ...scalar, type: "other" },
  discovery_status: { ...scalar, value: status },
} } });
jest.mock("@/stores/flowStore", () => ({ __esModule: true, default: (select: any) => select({ edges: [] }) }));
jest.mock("@/CustomNodes/helpers/get-node-input-colors", () => ({ getNodeInputColors: () => [] }));
jest.mock("@/CustomNodes/helpers/get-node-input-colors-name", () => ({ getNodeInputColorsName: () => [] }));
jest.mock("@/CustomNodes/helpers/sort-tool-mode-field", () => ({ sortToolModeFields: () => 0 }));
jest.mock("@/CustomNodes/utils/get-field-title", () => ({ __esModule: true, default: (_: any, name: string) => name }));
jest.mock("@/utils/reactflowUtils", () => ({ scapedJSONStringfy: JSON.stringify }));
jest.mock("./utils", () => ({ findPrimaryInput: () => ({ displayHandleMap: new Map([["pr_context", true]]), primaryInputFieldName: "pr_context" }) }));
jest.mock("../NodeInputField", () => ({ __esModule: true, default: (props: any) => <input aria-label={props.name} data-handle={String(props.displayHandle)} defaultValue={props.data.node.template[props.name].value || ""} /> }));
jest.mock("@/components/laomedoErrors/NodeErrorNotice", () => ({ __esModule: true, default: ({ label }: any) => <button>{label}</button> }));
function draw(data: any, showNode = true) {
  return <RenderInputParameters data={data} types={{}} isToolMode={false} showNode={showNode} shownOutputs={[]} showHiddenOutputs={false} />;
}
test("saved graphs display State before Labels, inline error after URL, and original sockets without rewriting values", () => {
  const data = node(); const saved = JSON.stringify(data);
  render(draw(data));
  expect(screen.getAllByRole("textbox").map(el => el.getAttribute("aria-label"))).toEqual(["repository_url", "state", "labels", "pr_choice", "pr_context"]);
  expect(screen.getByRole("textbox", { name: "repository_url" }).nextElementSibling).toBe(screen.getByRole("alert"));
  expect(screen.getByRole("alert")).toHaveTextContent(PR_DISCOVERY_ERROR);
  expect(screen.queryByRole("textbox", { name: "discovery_status" })).toBeNull();
  expect(screen.getByRole("textbox", { name: "state" })).toHaveValue("closed");
  for (const name of ["pr_context"]) expect(screen.getByRole("textbox", { name })).toHaveAttribute("data-handle", "true");
  expect(JSON.stringify(data)).toBe(saved);
});
test("empty, loading, failed, no matches and successful discovery remain distinguishable without raw messages", () => {
  const view = render(draw(node("Discovering GitHub PRs...")));
  expect(screen.getByRole("status")).toHaveTextContent("Discovering GitHub PRs...");
  view.rerender(draw(node("No matching PRs.")));
  expect(screen.getByRole("status")).toHaveTextContent("No matching PRs.");
  for (const status of ["2 matching PRs.", "private exception ghp_secret"]) {
    view.rerender(draw(node(status))); expect(screen.queryByRole("status")).toBeNull(); expect(screen.queryByRole("alert")).toBeNull();
  }
  const data = node(); data.node.template.repository_url.value = "";
  view.rerender(draw(data)); expect(screen.queryByRole("alert")).toBeNull();
  view.rerender(draw(node(), false)); expect(screen.queryByRole("alert")).toBeNull();
});
test("legacy selector flags get current choices without losing the selected value; unrelated nodes remain unchanged", () => {
  const data = node(); const field = data.node.template.state;
  expect(prFieldTemplate(data, "state", field)).toEqual({ ...field, advanced: false, options: ["open", "closed", "merged", "all"] });
  expect(prFieldTemplate(data, "labels", { combobox: true, value: ["backend"] }).combobox).toBe(false);
  expect(prChoicePlaceholder(data, "pr_choice")).toBe("Connection unavailable");
  const other = { ...data, type: "Other" };
  expect(prFieldTemplate(other, "state", field)).toBe(field);
  expect(prChoicePlaceholder(other, "labels", "default")).toBe("default");
  expect(isPRNode({ type: "ext:package:LaomedoGitHubPR@1" })).toBe(true);
});
