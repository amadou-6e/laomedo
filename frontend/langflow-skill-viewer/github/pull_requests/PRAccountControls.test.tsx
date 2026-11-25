import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import PRAccountControls from "./PRAccountControls";

const mockNode: any = { data: { node: { template: {
  github_connection: { value: "account-1" },
  repository_url: { value: "https://github.com/owner/repo" },
  pr_choice: { value: "", options: [] },
} } } };
const mockSetNode = jest.fn((_id, update) => { mockNode.data = update(mockNode).data; });
jest.mock("@/stores/flowStore", () => ({ __esModule: true, default: (select: any) => select({ setNode: mockSetNode }) }));
jest.mock("@/components/laomedoGitHubConnections/api", () => ({
  connectionCapability: async () => true,
  connectionRequest: async () => ({ index: { connections: [{ connection: { id: "account-1", state: "ready", principal: { login: "owner" }, mode: "browser", repositories: [{ id: 7, full_name: "owner/repo" }] } }] } }),
}));
jest.mock("@/modals/skillFilesModal/private/api", () => ({ subscribePrivateInvalidation: () => () => {} }));

beforeEach(() => {
  mockSetNode.mockClear();
  mockNode.data.node.template.github_connection.value = "account-1";
  mockNode.data.node.template.repository_url.value = "https://github.com/owner/repo";
  mockNode.data.node.template.pr_choice = { value: "", options: [] };
  global.fetch = jest.fn(async (url: any, options: any) => {
    if (!options.headers) throw new TypeError("The Langflow interceptor requires headers");
    return { ok: true, json: async () => String(url).includes("private-session") ? { ready: true, csrf_token: "test" } : { prs: [
    { choice: "#7 Private title", state: "open", labels: ["bug"] },
    { choice: "#8 Other title", state: "closed", labels: [] },
  ] } }; }) as any;
});

test("private PR search filters by qualifiers without storing private titles", async () => {
  const data = { id: "pr", node: mockNode.data.node };
  render(<PRAccountControls data={data} mode="selector" />);
  await waitFor(() => expect(mockSetNode).toHaveBeenCalled());
  const search = screen.getByRole("combobox", { name: "Pull request" });
  fireEvent.focus(search);
  fireEvent.change(search, { target: { value: "state:open label:bug" } });
  expect(screen.getByRole("option", { name: "#7 Private title" })).toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "#8 Other title" })).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole("option", { name: "#7 Private title" }));
  expect(mockNode.data.node.template.pr_choice.value).toBe("#7");
  expect(JSON.stringify(mockNode.data.node.template)).not.toContain("Private title");
});


test("account chooser exposes connected accounts and clears the previous repository", async () => {
  mockNode.data.node.template.github_connection.value = "";
  const data = { id: "pr", node: mockNode.data.node };
  render(<PRAccountControls data={data} mode="account" />);
  const account = await screen.findByRole("button", { name: "Account" });
  await waitFor(() => expect(account).toBeEnabled());
  fireEvent.click(account);
  fireEvent.click(await screen.findByRole("option", { name: "owner (browser)" }));
  expect(mockNode.data.node.template.github_connection.value).toBe("account-1");
  expect(mockNode.data.node.template.repository_url.value).toBe("");
});
