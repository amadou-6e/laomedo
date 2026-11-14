import { act, fireEvent, render, renderHook, screen, waitFor } from "@testing-library/react";
import Multiselect from "@/components/core/parameterRenderComponent/components/multiselectComponent";
import { useDropdownOptions } from "@/components/core/dropdownComponent/hooks/useDropdownOptions";
import { isValidConnection } from "@/utils/reactflowUtils";
import Dropdown from "@/components/core/dropdownComponent";
const mockData = { type: "LaomedoGitHubPR", node: { template: { repository_url: { value: "https://github.com/owner/repo" }, labels: { options: ["backend", "research"] } } } };
jest.mock("@/stores/flowStore", () => ({ __esModule: true, default: (select: any) => select({ nodes: [{ id: "pr", data: mockData }] }) }));
jest.mock("@/components/common/genericIconComponent", () => ({ __esModule: true, default: () => null }));
jest.mock("react-i18next", () => ({ ...jest.requireActual("react-i18next"), useTranslation: () => ({ t: (value: string) => value }) }));
jest.mock("@/controllers/API/queries/models/use-get-model-providers", () => ({ useGetModelProviders: () => ({}) }));
jest.mock("@/stores/flowsManagerStore", () => ({ __esModule: true, default: (select: any) => select({ currentFlowId: "flow" }) }));
jest.mock("@/components/core/dropdownComponent/hooks/useDropdownMutations", () => ({ useDropdownMutations: () => ({ handleRefreshButtonPress: jest.fn(), handleSourceOptions: jest.fn() }) }));
jest.mock("@/CustomNodes/GenericNode/components/NodeDialogComponent", () => ({ __esModule: true, default: () => null }));
beforeAll(() => {
  HTMLElement.prototype.scrollIntoView = jest.fn();
  global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} };
});
const props = { nodeId: "pr", value: [], options: ["backend", "research"], handleOnNewValue: jest.fn(), combobox: false, id: "labels", showParameter: true };
test("native PR Labels supports fuzzy discovered choices and does not create typed labels", async () => {
  render(<Multiselect {...props as any} />);
  fireEvent.click(screen.getByRole("combobox"));
  fireEvent.change(screen.getByPlaceholderText("input.searchOptions"), { target: { value: "bakend" } });
  await waitFor(() => expect(screen.getByText("backend", { exact: true })).toBeVisible());
  expect(screen.queryByText("research", { exact: true })).toBeNull();
  expect(screen.queryByText("bakend", { exact: true })).toBeNull();
  fireEvent.click(screen.getByText("backend", { exact: true }));
  expect(props.handleOnNewValue).toHaveBeenCalledWith({ value: ["backend"] });
});
test("native Labels refresh uses existing selection and newly returned options appear without a value change", async () => {
  const onChange = jest.fn();
  const view = render(<Multiselect {...props as any} options={[]} handleOnNewValue={onChange} />);
  fireEvent.click(screen.getByRole("combobox"));
  fireEvent.click(screen.getByRole("button", { name: "Refresh Labels" }));
  expect(onChange).toHaveBeenCalledWith({ value: [] }, { skipSnapshot: true });
  view.rerender(<Multiselect {...props as any} options={["new-label"]} handleOnNewValue={onChange} />);
  fireEvent.click(screen.getByRole("combobox"));
  await waitFor(() => expect(screen.getByText("new-label", { exact: true })).toBeVisible());
});

test("native PR search fuzzily narrows number/title options without creating arbitrary identities", async () => {
  const options = ["#264 Fix managed Codex recovery", "#263 Refactor activity"];
  const { result } = renderHook(() => useDropdownOptions({ value: "", options, validOptions: options, optionsMetaData: undefined, combobox: false, hasChildren: false, onSelect: jest.fn() }));
  await act(async () => { await result.current.searchRoleByTerm({ target: { value: "recovry" } } as any); });
  expect(result.current.filteredOptions).toEqual([options[0]]);
  await act(async () => { await result.current.searchRoleByTerm({ target: { value: "#263" } } as any); });
  expect(result.current.filteredOptions).toContain(options[1]);
  expect(result.current.filteredOptions.every(value => options.includes(value))).toBe(true);
  await act(async () => { await result.current.searchRoleByTerm({ target: { value: "nonexistent xyzzy" } } as any); });
  expect(result.current.filteredOptions).toEqual([]);
});

test("Enter in the native PR search cannot submit the typed term as a new PR identity", async () => {
  const select = jest.fn(); const direct = jest.fn(); const options = ["#264 Fix managed Codex recovery"];
  render(<Dropdown {...{ nodeId: "pr", name: "pr_choice", value: "", options, combobox: false, onSelect: select, handleOnNewValue: direct } as any} />);
  fireEvent.click(screen.getByRole("combobox"));
  const input = screen.getByTestId("dropdown_search_input");
  fireEvent.change(input, { target: { value: "recovry" } });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(select.mock.calls.every(call => options.includes(call[0]))).toBe(true);
  expect(direct).not.toHaveBeenCalled();
});

test("native canvas permits only the direct PR/Agent return cycle in either wiring order", () => {
  const pr = { id: "pr", data: { type: "LaomedoGitHubPR", node: { template: { pr_context: { list: false }, operation: { list: false } } } } };
  const agent = { id: "agent", data: { type: "LaomedoCodexAgent", node: { template: { task: { list: false } } } } };
  const forward = { source: "pr", target: "agent", sourceHandle: JSON.stringify({ id: "pr", dataType: "LaomedoGitHubPR", name: "pr", output_types: ["JSON"] }), targetHandle: JSON.stringify({ id: "agent", fieldName: "task", inputTypes: ["Message", "Data"], type: "str" }) };
  const backward = { source: "agent", target: "pr", sourceHandle: JSON.stringify({ id: "agent", dataType: "LaomedoCodexAgent", name: "answer", output_types: ["Message"] }), targetHandle: JSON.stringify({ id: "pr", fieldName: "pr_context", inputTypes: ["Message", "Data"], type: "other" }) };
  expect(isValidConnection(backward as any, [pr, agent] as any, [{ ...forward, id: "forward" }] as any)).toBe(true);
  expect(isValidConnection(forward as any, [pr, agent] as any, [{ ...backward, id: "backward" }] as any)).toBe(true);
  const unrelated = { ...pr, data: { ...pr.data, type: "Other" } };
  expect(isValidConnection(backward as any, [unrelated, agent] as any, [{ ...forward, id: "forward" }] as any)).toBe(false);
  const legacy = { ...backward, targetHandle: JSON.stringify({ id: "pr", fieldName: "operation", inputTypes: ["Message", "Data"], type: "other" }) };
  expect(isValidConnection(legacy as any, [pr, agent] as any, [{ ...forward, id: "forward" }] as any)).toBe(false);
});
