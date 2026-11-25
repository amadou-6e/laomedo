import { useState } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import PrivateSkillControls, { SkillSourceSuggestions } from "./PrivateSkillControls";
import { api } from "@/controllers/API/api";
import { connectionRequest } from "@/components/laomedoGitHubConnections/api";
import { privateSkillRequest } from "./api";

let setNode: any;
jest.mock("@/stores/flowStore", () => {
  const apply = (...args: any[]) => setNode(...args);
  return { __esModule: true, default: (select: any) => select({ setNode: apply }) };
});
const mockSourceChange = jest.fn();
const mockQueryClient = { fetchQuery: ({ queryFn }: any) => queryFn() };
jest.mock("@/CustomNodes/hooks/use-handle-new-value", () => ({ __esModule: true, default: () => ({ handleOnNewValue: mockSourceChange }) }));
jest.mock("@/stores/authStore", () => ({ __esModule: true, default: (select: any) => select({ userData: { id: "profile" } }) }));
jest.mock("@tanstack/react-query", () => ({ useQueryClient: () => mockQueryClient }));
jest.mock("@/controllers/API/api", () => ({ api: { get: jest.fn() } }));
jest.mock("@/controllers/API/helpers/constants", () => ({ getURL: () => "/api/v1/flows" }));
jest.mock("@/components/laomedoGitHubConnections/api", () => ({ connectionCapability: async () => true, connectionRequest: jest.fn(), ConnectionFailure: class extends Error { constructor(public code: string) { super(code); } } }));
jest.mock("./api", () => ({ privateSkillRequest: jest.fn(), subscribePrivateInvalidation: () => () => {} }));
jest.mock("@/components/laomedoErrors/ErrorExplanation", () => ({ __esModule: true, default: () => <p>Access refused</p> }));
jest.mock("@/components/laomedoErrors/NodeErrorNotice", () => ({ __esModule: true, default: () => <p>Access refused</p> }));
jest.mock("@/components/laomedoErrors/nodeErrors", () => ({ describeNodeFailure: (code: string) => ({ code }) }));
const chosen = "synthetic | skills/synthetic";
const commit = "a".repeat(40), hash = "sha256:" + "b".repeat(64);
const index = { revision: 1, connections: [{ connection: { id: "selected", state: "ready", mode: "token", principal: { login: "Account" }, repositories: [{ id: 456, full_name: "synthetic/private" }] } }], pending: [] };
const origin = { label: "heads/main", commit, skill_id: "private-id", revision_id: hash };
function Harness({ initialConnection = "selected", initialSkill = "" }) {
  const [data, setData] = useState<any>({ id: "skill", node: { template: Object.fromEntries(Object.entries({ github_connection: initialConnection,
    source: "https://github.com/synthetic/private", discovery_status: "Discovery failed. Check source access and refresh.", skill_id: initialSkill, revision_id: "saved-pin", resolved_skill_id: "saved-id", resolved_revision_id: "saved-hash", resolved_selection: "saved-binding", private_repository_id: "" }).map(([name, value]) => [name, { value }])) } });
  setNode = (_id: string, change: any) => setData((old: any) => change({ data: old }).data);
  return <><PrivateSkillControls data={data} /><output data-testid="template">{JSON.stringify(data.node.template)}</output>
    <button onClick={() => setData((old: any) => ({ ...old, node: { template: { ...old.node.template, skill_id: { value: chosen } } } }))}>Choose discovered Skill</button>
    <button onClick={() => setData((old: any) => ({ ...old, node: { template: { ...old.node.template, revision_id: { value: `heads/main @ ${commit}` } } } }))}>Choose discovered revision</button></>;
}
const template = () => JSON.parse(screen.getByTestId("template").textContent || "{}");
beforeEach(() => { jest.clearAllMocks(); (connectionRequest as jest.Mock).mockResolvedValue({ index });
  (privateSkillRequest as jest.Mock).mockImplementation((action: string) => Promise.resolve(action === "discover" ? { skills: [{ choice: chosen }] } : { revisions: [origin] })); });

test("source suggestions show the selected connection's repositories and saved sources for that connection", async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: [{ user_id: "profile", data: { nodes: [
    { data: { type: "LaomedoGitHubSkill", node: { template: { github_connection: { value: "selected" }, source: { value: "https://github.com/synthetic/earlier" } } } } },
    { data: { type: "LaomedoGitHubSkill", node: { template: { github_connection: { value: "other" }, source: { value: "https://github.com/other/private" } } } } },
  ] } }] });
  render(<SkillSourceSuggestions data={{ id: "skill", type: "LaomedoGitHubSkill", node: { template: { github_connection: { value: "selected" } } } }} />);
  fireEvent.click(screen.getByRole("button", { name: "Show sources and repositories" }));
  fireEvent.click(await screen.findByRole("option", { name: "synthetic/private" }));
  expect(mockSourceChange).toHaveBeenCalledWith({ value: "https://github.com/synthetic/private" });
  fireEvent.click(screen.getByRole("button", { name: "Show sources and repositories" }));
  expect(await screen.findByRole("option", { name: "synthetic/earlier" })).toBeVisible();
  expect(screen.queryByText("https://github.com/other/private")).toBeNull();
});

test("source combobox supports keyboard selection and ignores other profiles' saved workflows", async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: [
    { user_id: "other-profile", data: { nodes: [{ data: { type: "LaomedoGitHubSkill", node: { template: { source: { value: "/other-user" } } } } }] } },
    { user_id: "profile", data: { nodes: [{ data: { type: "LaomedoGitHubSkill", node: { template: { source: { value: "/my-source" } } } } }] } },
  ] });
  render(<SkillSourceSuggestions data={{ id: "skill", type: "LaomedoGitHubSkill", node: { template: {} } }} />);
  const input = screen.getByRole("combobox", { name: "Repository" });
  fireEvent.focus(input);
  expect(await screen.findByRole("option", { name: "/my-source" })).toBeVisible();
  expect(screen.queryByText("/other-user")).toBeNull();
  fireEvent.keyDown(input, { key: "ArrowDown" });
  fireEvent.keyDown(input, { key: "Enter" });
  expect(mockSourceChange).toHaveBeenCalledWith({ value: "/my-source" });
  expect(input).toHaveAttribute("aria-expanded", "false");
});

test("opening a populated source shows the other repositories without clearing the selection", async () => {
  (api.get as jest.Mock).mockResolvedValue({ data: [] });
  render(<SkillSourceSuggestions data={{ id: "skill", type: "LaomedoGitHubSkill", node: { template: { github_connection: { value: "selected" }, source: { value: "https://github.com/synthetic/old" } } } }} />);
  const input = screen.getByRole("combobox", { name: "Repository" });
  expect(input).toHaveValue("synthetic/old");
  fireEvent.focus(input);
  expect(input).toHaveValue("https://github.com/synthetic/old");
  fireEvent.blur(input);
  expect(input).toHaveValue("synthetic/old");
  fireEvent.click(screen.getByRole("button", { name: "Show sources and repositories" }));
  expect(await screen.findByRole("option", { name: "synthetic/private" })).toBeVisible();
  expect(mockSourceChange).not.toHaveBeenCalled();
});

test("selecting a connection clears the old anonymous error and discovers private skills", async () => {
  render(<Harness initialConnection="" />);
  const select = await screen.findByLabelText("Connection");
  fireEvent.focus(select);
  await screen.findByText("Account (token)");
  fireEvent.change(select, { target: { value: "selected" } });
  await waitFor(() => expect(template().github_connection.value).toBe("selected"));
  expect(template().discovery_status.value).toBe("");
  await waitFor(() => expect(template().skill_id.options).toEqual([chosen]));
});

test("private discovery populates native dropdowns and exact revision binding", async () => {
  render(<Harness />);
  await waitFor(() => expect(template().skill_id.options).toEqual([chosen]));
  expect(template().skill_id.value).toBe("");
  fireEvent.click(screen.getByText("Choose discovered Skill"));
  await waitFor(() => expect(template().revision_id.options).toEqual([`heads/main @ ${commit}`]));
  fireEvent.click(screen.getByText("Choose discovered revision"));
  await waitFor(() => expect(template().resolved_revision_id.value).toBe(hash));
  expect(JSON.parse(template().resolved_selection.value)).toEqual(["https://github.com/synthetic/private", chosen, `heads/main @ ${commit}`, "selected"]);
  expect(template().private_repository_id.value).toBe("456");
});

test("changing connection clears pins and rejects late discovery", async () => {
  let finish: (value: unknown) => void = () => {};
  (privateSkillRequest as jest.Mock).mockImplementation(() => new Promise((resolve) => { finish = resolve; }));
  render(<Harness />);
  await waitFor(() => expect(privateSkillRequest).toHaveBeenCalled());
  // Busy controls intentionally prevent changing authority until the request ends;
  // a programmatic context change still has to invalidate the epoch.
  fireEvent.change(screen.getByLabelText("Connection"), { target: { value: "" } });
  await act(async () => finish({ skills: [{ choice: chosen }] }));
  await waitFor(() => expect(template().github_connection.value).toBe(""));
  expect(template().skill_id.value).toBe("");
  expect(template().resolved_revision_id.value).toBe("");
  expect(template().skill_id.options).toEqual([]);
});

test("private failure preserves stored pins and never requests anonymous discovery", async () => {
  (privateSkillRequest as jest.Mock).mockRejectedValue(new Error("synthetic failure"));
  render(<Harness initialSkill={chosen} />);
  await screen.findByText("Access refused");
  expect(template().skill_id.value).toBe(chosen);
  expect(template().revision_id.value).toBe("saved-pin");
  expect(template().resolved_revision_id.value).toBe("saved-hash");
  expect((privateSkillRequest as jest.Mock).mock.calls.every((args) => args[1].connectionId === "selected")).toBe(true);
});
