import { useState } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import PrivateSkillControls from "./PrivateSkillControls";
import { connectionRequest } from "@/components/laomedoGitHubConnections/api";
import { privateSkillRequest } from "./api";

let setNode: any;
jest.mock("@/stores/flowStore", () => {
  const apply = (...args: any[]) => setNode(...args);
  return { __esModule: true, default: (select: any) => select({ setNode: apply }) };
});
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
    source: "https://github.com/synthetic/private", skill_id: initialSkill, revision_id: "saved-pin", resolved_skill_id: "saved-id", resolved_revision_id: "saved-hash", resolved_selection: "saved-binding", private_repository_id: "" }).map(([name, value]) => [name, { value }])) } });
  setNode = (_id: string, change: any) => setData((old: any) => change({ data: old }).data);
  return <><PrivateSkillControls data={data} /><output data-testid="template">{JSON.stringify(data.node.template)}</output>
    <button onClick={() => setData((old: any) => ({ ...old, node: { template: { ...old.node.template, skill_id: { value: chosen } } } }))}>Choose discovered Skill</button>
    <button onClick={() => setData((old: any) => ({ ...old, node: { template: { ...old.node.template, revision_id: { value: `heads/main @ ${commit}` } } } }))}>Choose discovered revision</button></>;
}
const template = () => JSON.parse(screen.getByTestId("template").textContent || "{}");
beforeEach(() => { jest.clearAllMocks(); (connectionRequest as jest.Mock).mockResolvedValue({ index });
  (privateSkillRequest as jest.Mock).mockImplementation((action: string) => Promise.resolve(action === "discover" ? { skills: [{ choice: chosen }] } : { revisions: [origin] })); });

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
