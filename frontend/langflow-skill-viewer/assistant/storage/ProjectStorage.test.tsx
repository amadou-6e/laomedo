import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ProjectStorage from "./ProjectStorage";
import { AssistantFailure, assistantRequest } from "../api";
import type { ProjectStorageState } from "./models";
jest.mock("../api", () => ({ ...jest.requireActual("../api"), assistantRequest: jest.fn() }));

const state: ProjectStorageState = {
  repositories: [{id: "repo", name: "Project", path: "C:/project"}],
  agent_files: {repository_id: "repo", path: "agent-files"},
  graphs: {first: {location: {repository_id: "repo", path: "graphs/first.json"}, sha256: "old", current_sha256: "current", availability: "available"}},
  workflows: [{id: "first", name: "First graph", revision: "rev1"}, {id: "second", name: "Second graph", revision: "rev2"}],
};
beforeEach(() => {
  jest.clearAllMocks();
  jest.mocked(assistantRequest).mockImplementation(async path => path === "/storage" ? state : {diagnostics: []});
});

it("uses each graph's location and observed file/app revisions", async () => {
  render(<ProjectStorage onFailure={jest.fn()} />);
  fireEvent.click(screen.getByRole("button", {name: "Project storage"}));
  await screen.findByText("Current: Project / agent-files");
  expect(screen.queryByText(/C:\/project/)).not.toBeInTheDocument();
  expect(screen.getByText(/app-owned checkout/)).toBeInTheDocument();
  await waitFor(() => expect(screen.getByLabelText("Graph")).not.toBeDisabled());
  fireEvent.change(screen.getByLabelText("Graph"), {target: {value: "first"}});
  expect(screen.getByLabelText("Graph JSON file")).toHaveValue("graphs/first.json");
  fireEvent.click(screen.getByRole("button", {name: "Save graph file"}));
  await screen.findByText("Graph file saved.");
  expect(assistantRequest).toHaveBeenCalledWith("/storage/graphs/first/save", {
    location: {repository_id: "repo", path: "graphs/first.json"}, expected_graph_revision: "rev1", expected_file_hash: "current",
  }, expect.any(AbortSignal));
  fireEvent.change(screen.getByLabelText("Graph"), {target: {value: "second"}});
  expect(screen.getByLabelText("Graph JSON file")).toHaveValue("graphs/second.json");
  expect(screen.getByRole("button", {name: "Load graph file"})).toBeDisabled();
});

it("retains input after a stale write and never retries it automatically", async () => {
  jest.mocked(assistantRequest).mockImplementation(async path => {
    if (path === "/storage") return state;
    throw new AssistantFailure("assistant_storage_file_changed");
  });
  render(<ProjectStorage onFailure={jest.fn()} />);
  fireEvent.click(screen.getByRole("button", {name: "Project storage"}));
  await screen.findByText("Current: Project / agent-files");
  await waitFor(() => expect(screen.getByLabelText("Graph")).not.toBeDisabled());
  fireEvent.change(screen.getByLabelText("Graph"), {target: {value: "first"}});
  fireEvent.click(screen.getByRole("button", {name: "Save graph file"}));
  expect((await screen.findByRole("alert")).textContent).toContain("file changed");
  expect(screen.getByLabelText("Graph JSON file")).toHaveValue("graphs/first.json");
  expect(jest.mocked(assistantRequest).mock.calls.filter(call => call[0].endsWith("/save"))).toHaveLength(1);
});

it("does not load when the replacement confirmation is cancelled", async () => {
  render(<ProjectStorage onFailure={jest.fn()} />);
  fireEvent.click(screen.getByRole("button", {name: "Project storage"}));
  await screen.findByText("Current: Project / agent-files");
  await waitFor(() => expect(screen.getByLabelText("Graph")).not.toBeDisabled());
  fireEvent.change(screen.getByLabelText("Graph"), {target: {value: "first"}});
  fireEvent.click(screen.getByRole("button", {name: "Load graph file"}));
  expect(await screen.findByRole("dialog", {name: "Replace saved graph?"})).toHaveTextContent("First graph");
  fireEvent.click(screen.getByRole("button", {name: "Cancel load"}));
  expect(jest.mocked(assistantRequest).mock.calls.some(call => call[0].endsWith("/load"))).toBe(false);
});

it("clones the selected remote and clears the one-use credential", async () => {
  render(<ProjectStorage onFailure={jest.fn()} />);
  fireEvent.click(screen.getByRole("button", {name: "Project storage"}));
  await screen.findByText("Current: Project / agent-files");
  await waitFor(() => expect(screen.getByLabelText("Repository name")).not.toBeDisabled());
  fireEvent.change(screen.getByLabelText("Repository name"), {target: {value: "New project"}});
  fireEvent.change(screen.getByLabelText("GitHub repository"), {target: {value: "example/project"}});
  fireEvent.change(screen.getByLabelText("Read token (optional for private repositories)"), {target: {value: "one-use-test-token"}});
  fireEvent.click(screen.getByRole("button", {name: "Clone repository"}));
  await screen.findByText("Repository cloned.");
  expect(assistantRequest).toHaveBeenCalledWith("/storage/repositories/clone", {name: "New project", repository: "example/project", token: "one-use-test-token"}, expect.any(AbortSignal), undefined, 120000);
  expect(screen.getByLabelText("Read token (optional for private repositories)")).toHaveValue("");
  expect(screen.getByLabelText("Agent repository")).toHaveValue("repo");
});

it("loads only after the user confirms the selected graph replacement", async () => {
  render(<ProjectStorage activeGraphId="first" onFailure={jest.fn()} />);
  fireEvent.click(screen.getByRole("button", {name: "Project storage"}));
  await screen.findByText("Current: Project / agent-files");
  await waitFor(() => expect(screen.getByRole("button", {name: "Load graph file"})).not.toBeDisabled());
  fireEvent.click(screen.getByRole("button", {name: "Load graph file"}));
  await screen.findByRole("dialog", {name: "Replace saved graph?"});
  expect(jest.mocked(assistantRequest).mock.calls.some(call => call[0].endsWith("/load"))).toBe(false);
  fireEvent.click(screen.getByRole("button", {name: "Replace saved graph"}));
  await screen.findByText(/Graph file loaded/);
  expect(assistantRequest).toHaveBeenCalledWith("/storage/graphs/first/load", {
    location: {repository_id: "repo", path: "graphs/first.json"}, expected_graph_revision: "rev1", expected_file_hash: "current",
  }, expect.any(AbortSignal));
});

it("opens on the graph being edited with its own persisted file location", async () => {
  render(<ProjectStorage activeGraphId="first" onFailure={jest.fn()} />);
  fireEvent.click(screen.getByRole("button", {name: "Project storage"}));
  await waitFor(() => expect(screen.getByLabelText("Graph")).toHaveValue("first"));
  expect(screen.getByLabelText("Graph JSON file")).toHaveValue("graphs/first.json");
  expect(screen.getByLabelText("Graph repository")).toHaveValue("repo");
});
