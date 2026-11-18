import { StrictMode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ProviderConnections from "./ProviderConnections";
import { saveGoConnection, beginLogin, cancelLogin, listConnections, readProgress, inspectDisconnect, disconnect, retryCleanup } from "./api";

jest.mock("@/components/common/genericIconComponent", () => ({ __esModule: true, default: () => <span /> }));

jest.mock("@/components/ui/button", () => ({
  Button: ({ ignoreTitleCase, variant, children, ...props }) => <button {...props}>{children}</button>,
}));
jest.mock("./api", () => ({ ...jest.requireActual("./api"), saveGoConnection: jest.fn(), beginLogin: jest.fn(), cancelLogin: jest.fn(), listConnections: jest.fn(), readProgress: jest.fn(), inspectDisconnect: jest.fn(), disconnect: jest.fn(), retryCleanup: jest.fn() }));

jest.mock("./assets/opencode-logo-dark.svg", () => "opencode-dark.svg");
jest.mock("./assets/opencode-logo-light.svg", () => "opencode-light.svg");

describe("saved provider Settings", () => {
  const account = { connection_id: "00000000-0000-4000-8000-000000000001", provider: "codex", method: "chatgpt_plan_oauth", label: "Work account", generation: 1, auth_state: "ready", lifecycle: "connected" };
  beforeEach(() => {
    jest.clearAllMocks();
    sessionStorage.clear();
    window.history.replaceState(null, "", "/settings/providers");
    (listConnections as jest.Mock).mockResolvedValue([]);
  });

  it("saves an explicitly selected Go key and clears it after failure", async () => {
    (saveGoConnection as jest.Mock).mockRejectedValue(new Error("unavailable"));
    render(<ProviderConnections />);
    await screen.findByText("No providers connected");
    fireEvent.click(screen.getByRole("button", { name: "Add provider" }));
    fireEvent.click(screen.getByRole("button", { name: "OpenCode" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(beginLogin).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText("Connection name"), { target: { value: "My Go plan" } });
    fireEvent.change(screen.getByLabelText("OpenCode Go key"), { target: { value: "fixture-go-key" } });
    fireEvent.click(screen.getByRole("button", { name: "Save connection" }));
    await waitFor(() => expect(saveGoConnection).toHaveBeenCalledWith("fixture-go-key", "My Go plan"));
    expect((screen.getByLabelText("OpenCode Go key") as HTMLInputElement).value).toBe("");
    expect(sessionStorage.length).toBe(0);
  });

  it("loads under StrictMode without starting native sign-in", async () => {
    render(<StrictMode><ProviderConnections /></StrictMode>);
    await screen.findByText("No providers connected");
    expect(beginLogin).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(listConnections).toHaveBeenCalledTimes(3));
    expect(beginLogin).not.toHaveBeenCalled();
  });

  it("discloses affected work and waits for explicit Disconnect confirmation", async () => {
    (listConnections as jest.Mock).mockResolvedValue([account]);
    (inspectDisconnect as jest.Mock).mockResolvedValue({ connection_id: account.connection_id, generation: 1, active_runs: 2, revision: 7 });
    (disconnect as jest.Mock).mockResolvedValue({ connection_id: account.connection_id, status: "removed" });
    render(<ProviderConnections />);
    fireEvent.click(await screen.findByRole("button", { name: /Work account/ }));
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    await screen.findByRole("heading", { name: "Disconnect Codex?" });
    expect(screen.getByText(/2 active runs will stop/)).toBeTruthy();
    expect(disconnect).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    await screen.findByRole("heading", { name: "Disconnected" });
    expect(disconnect).toHaveBeenCalledTimes(1);
    expect(beginLogin).not.toHaveBeenCalled();
  });

  it("keeps failed cleanup visible and offers an explicit retry", async () => {
    (listConnections as jest.Mock).mockResolvedValue([account]);
    (inspectDisconnect as jest.Mock).mockResolvedValue({ connection_id: account.connection_id, generation: 1, active_runs: 0, revision: 1 });
    (disconnect as jest.Mock).mockResolvedValue({ connection_id: account.connection_id, status: "cleanup_required" });
    (retryCleanup as jest.Mock).mockResolvedValue({ connection_id: account.connection_id, status: "removed" });
    render(<ProviderConnections />);
    fireEvent.click(await screen.findByRole("button", { name: /Work account/ }));
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    await screen.findByRole("heading", { name: "Disconnect Codex?" });
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    await screen.findByRole("heading", { name: "Cleanup required" });
    expect(retryCleanup).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Retry cleanup" }));
    await screen.findByRole("heading", { name: "Disconnected" });
    expect(retryCleanup).toHaveBeenCalledWith(account.connection_id);
  });

  it("chooses type and method before an explicit sign-in action", async () => {
    render(<ProviderConnections />);
    await screen.findByText("No providers connected");
    fireEvent.click(screen.getByRole("button", { name: "Add provider" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText(/Sign in with ChatGPT to use/)).toBeTruthy();
    expect(beginLogin).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Back to connections" }).querySelector("svg")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Back to connections" }));
    expect(screen.getByRole("heading", { name: "Add provider" })).toBeTruthy();
  });

  it("does not claim removal or poll when Disconnect was not confirmed", async () => {
    (listConnections as jest.Mock).mockResolvedValue([account]);
    (inspectDisconnect as jest.Mock).mockResolvedValue({ connection_id: account.connection_id, generation: 1, active_runs: 0, revision: 1 });
    (disconnect as jest.Mock).mockRejectedValue(new Error("network unavailable"));
    render(<ProviderConnections />);
    fireEvent.click(await screen.findByRole("button", { name: /Work account/ }));
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    await screen.findByRole("heading", { name: "Disconnect Codex?" });
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    await screen.findByRole("heading", { name: "Check connection" });
    expect(screen.getByRole("status")).toHaveTextContent("Disconnect wasn’t confirmed");
    expect(screen.queryByText(/Stopping active work/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(listConnections).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("heading", { name: "Check connection" })).toBeTruthy();
  });

  it("forgets a settled callback receipt before later Refresh", async () => {
    const id = "00000000-0000-4000-8000-000000000002";
    window.history.replaceState(null, "", "/settings/providers?attempt=" + id);
    (listConnections as jest.Mock).mockResolvedValue([account]);
    (readProgress as jest.Mock).mockResolvedValue({ attempt_id: id, status: "connected", connection_id: account.connection_id, code: null });
    render(<ProviderConnections />);
    await screen.findByRole("heading", { name: "Work account" });
    expect(window.location.search).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(listConnections).toHaveBeenCalledTimes(2));
    expect(readProgress).toHaveBeenCalledTimes(1);
    expect(beginLogin).not.toHaveBeenCalled();
  });

  it("keeps saved rows visible if refresh fails", async () => {
    (listConnections as jest.Mock).mockResolvedValue([{ connection_id: "00000000-0000-4000-8000-000000000001", provider: "codex", method: "chatgpt_plan_oauth", label: "Work account", generation: 1, auth_state: "ready" }]);
    render(<ProviderConnections />);
    await screen.findByText("Work account");
    (listConnections as jest.Mock).mockRejectedValue(new Error("private raw failure"));
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByRole("alert");
    expect(screen.getByText("Work account")).toBeTruthy();
    expect(screen.queryByText("private raw failure")).toBeNull();
    expect(screen.queryByText("No providers connected")).toBeNull();
  });

  it("restores only an opaque pending receipt without relaunching login", async () => {
    sessionStorage.setItem("laomedo.provider-attempt", "00000000-0000-4000-8000-000000000002");
    (readProgress as jest.Mock).mockResolvedValue({ attempt_id: "00000000-0000-4000-8000-000000000002", status: "connecting", connection_id: null, code: null });
    render(<ProviderConnections />);
    await screen.findByText("Waiting for sign-in…");
    expect(beginLogin).not.toHaveBeenCalled();
    expect(sessionStorage.length).toBe(1);
  });

  it("checks an uncertain save before enabling another sign-in", async () => {
    const id = "00000000-0000-4000-8000-000000000002";
    sessionStorage.setItem("laomedo.provider-attempt", id);
    (readProgress as jest.Mock).mockResolvedValue({ attempt_id: id, status: "failed", connection_id: null, code: "provider_save_unconfirmed" });
    render(<ProviderConnections />);
    await screen.findByRole("heading", { name: "Check connection" });
    expect(screen.getByRole("button", { name: "Try again" })).toBeDisabled();
    expect(screen.queryByText(/Your saved connection hasn’t changed/)).toBeNull();
    (readProgress as jest.Mock).mockResolvedValue({ attempt_id: id, status: "failed", connection_id: null, code: "provider_sign_in_failed" });
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByRole("heading", { name: "Sign-in failed" });
    expect(screen.getByRole("button", { name: "Try again" })).not.toBeDisabled();
    expect(beginLogin).not.toHaveBeenCalled();
  });

  it("recovers an unconfirmed callback from its stored receipt after a failed read", async () => {
    const id = "00000000-0000-4000-8000-000000000002";
    window.history.replaceState(null, "", "/settings/providers?login=unconfirmed");
    sessionStorage.setItem("laomedo.provider-attempt", id);
    (listConnections as jest.Mock).mockRejectedValueOnce(new Error("temporary network failure")).mockResolvedValue([account]);
    (readProgress as jest.Mock).mockResolvedValue({ attempt_id: id, status: "connected", connection_id: account.connection_id, code: null });
    render(<ProviderConnections />);
    await screen.findByRole("alert");
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByRole("heading", { name: "Work account" });
    expect(readProgress).toHaveBeenCalledWith(id);
    expect(beginLogin).not.toHaveBeenCalled();
  });

  it("keeps an unconfirmed callback without a receipt readable and lets Back leave", async () => {
    window.history.replaceState(null, "", "/settings/providers?login=unconfirmed");
    render(<ProviderConnections />);
    await screen.findByRole("heading", { name: "Check connection" });
    await waitFor(() => expect(screen.getByRole("button", { name: "Refresh" })).not.toBeDisabled());
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(listConnections).toHaveBeenCalledTimes(2));
    expect(screen.getByRole("button", { name: "Try again" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Back to connections" }));
    await screen.findByRole("heading", { name: "Providers" });
    expect(cancelLogin).not.toHaveBeenCalled();
    expect(beginLogin).not.toHaveBeenCalled();
  });
});
