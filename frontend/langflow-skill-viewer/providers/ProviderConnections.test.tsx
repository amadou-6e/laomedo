import { StrictMode } from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import ProviderConnections from "./ProviderConnections";
import { saveGoConnection, beginLogin, cancelLogin, listConnections, readProgress, readClaudeAttempt, inspectDisconnect, disconnect, retryCleanup, ProviderFailure } from "./api";

jest.mock("@/components/common/genericIconComponent", () => ({ __esModule: true, default: () => <span /> }));
jest.mock("@/assets/LangflowLogo.svg?react", () => ({ __esModule: true, default: (props) => <svg {...props} /> }));

jest.mock("@/components/ui/button", () => ({
  Button: ({ ignoreTitleCase, variant, asChild, children, ...props }) => asChild ? children : <button {...props}>{children}</button>,
}));
jest.mock("./api", () => ({ ...jest.requireActual("./api"), saveGoConnection: jest.fn(), beginLogin: jest.fn(), cancelLogin: jest.fn(), listConnections: jest.fn(), readProgress: jest.fn(), readClaudeAttempt: jest.fn(), inspectDisconnect: jest.fn(), disconnect: jest.fn(), retryCleanup: jest.fn() }));

jest.mock("./assets/openai-logo.svg", () => "openai-logo.svg");

jest.mock("./assets/opencode-logo-dark.svg", () => "opencode-dark.svg");
jest.mock("./assets/opencode-logo-light.svg", () => "opencode-light.svg");

describe("saved provider Settings", () => {
  const account = { connection_id: "00000000-0000-4000-8000-000000000001", provider: "codex", method: "chatgpt_plan_oauth", label: "Work account", generation: 1, auth_state: "ready", lifecycle: "connected" };
  beforeEach(() => {
    jest.clearAllMocks();
    sessionStorage.clear();
    window.history.replaceState(null, "", "/settings/providers");
    (listConnections as jest.Mock).mockResolvedValue([]);
    jest.spyOn(window, "open").mockReturnValue(null);
  });

  it("keeps the Claude code field focused and selected during background polling", async () => {
    let poll: () => void = () => {};
    const interval = jest.spyOn(window, "setInterval").mockImplementation(callback => { poll = callback as () => void; return 1; });
    try {
      const progress = {attempt_id: "fixture", provider: "claude", status: "connecting", connection_id: null, code: null};
      const authorization_url = "https://claude.com/cai/oauth/authorize?state=fixture";
      (listConnections as jest.Mock).mockResolvedValue([{...account, provider: "claude", method: "claude_native"}]);
      (beginLogin as jest.Mock).mockResolvedValue({progress, authorization_url});
      (readProgress as jest.Mock).mockResolvedValue(progress);
      (readClaudeAttempt as jest.Mock).mockResolvedValue({progress, authorization_url});
      render(<ProviderConnections />);
      fireEvent.click(await screen.findByRole("button", {name: /View connection for/}));
      fireEvent.click(screen.getByRole("button", {name: "Sign in again"}));
      fireEvent.click(await screen.findByRole("link", {name: "Continue to Claude"}));
      const code = screen.getByLabelText("Claude sign-in code") as HTMLInputElement;
      fireEvent.change(code, {target: {value: "fixture-code"}});
      code.focus(); code.setSelectionRange(0, 7);
      let complete!: (value: unknown) => void;
      (listConnections as jest.Mock).mockReturnValueOnce(new Promise(resolve => {complete = resolve;}));
      act(() => poll());
      expect(code).not.toBeDisabled();
      expect(code).toHaveFocus();
      expect(code.selectionEnd).toBe(7);
      await act(async () => complete([]));
      expect(code).toHaveFocus();
      expect(code.selectionEnd).toBe(7);
    } finally { interval.mockRestore(); }
  });

  it("returns from adding a Go key to its connection and emphasizes saved custody", async () => {
    (listConnections as jest.Mock).mockResolvedValue([{ ...account, provider: "opencode", method: "opencode_go_key", auth_state: "unavailable" }]);
    render(<ProviderConnections />);
    expect(await screen.findByText("Key saved")).toHaveClass("gc-ready");
    fireEvent.click(screen.getByRole("button", { name: /View connection for/ }));
    fireEvent.click(screen.getByRole("button", { name: "Add another Go key" }));
    fireEvent.click(screen.getByRole("button", { name: "Back to connections" }));
    expect(screen.getByRole("button", { name: "Add another Go key" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Add provider" })).toBeNull();
  });

  it("starts reauthentication directly and reveals the Claude code only after continuing", async () => {
    const progress = { attempt_id: "fixture", provider: "claude", status: "connecting", connection_id: null, code: null };
    const authorization_url = "https://claude.com/cai/oauth/authorize?state=fixture";
    (listConnections as jest.Mock).mockResolvedValue([{ ...account, provider: "claude", method: "claude_native" }]);
    (beginLogin as jest.Mock).mockResolvedValue({ progress, authorization_url });
    (readProgress as jest.Mock).mockResolvedValue(progress);
    (readClaudeAttempt as jest.Mock).mockResolvedValue({ progress, authorization_url });
    render(<ProviderConnections />);
    fireEvent.click(await screen.findByRole("button", { name: /View connection for/ }));
    fireEvent.click(screen.getByRole("button", { name: "Sign in again" }));
    const link = await screen.findByRole("link", { name: "Continue to Claude" });
    expect(beginLogin).toHaveBeenCalledWith(account.connection_id, "claude");
    expect(screen.queryByRole("button", { name: "Continue to sign in" })).toBeNull();
    expect(screen.queryByLabelText("Claude sign-in code")).toBeNull();
    fireEvent.click(link);
    expect(screen.getByLabelText("Claude sign-in code")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Finish sign-in" })).toBeDisabled();
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
    await screen.findByRole("heading", { name: "Check connection" });
    expect(screen.queryByLabelText("OpenCode Go key")).toBeNull();
    expect(screen.getByRole("button", { name: "Try again" })).toBeDisabled();
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

  it("starts the selected browser provider directly from Continue", async () => {
    (beginLogin as jest.Mock).mockResolvedValue({ progress: { attempt_id: "fixture", provider: "codex", status: "connecting", connection_id: null, code: null }, authorization_url: null });
    render(<ProviderConnections />);
    await screen.findByText("No providers connected");
    fireEvent.click(screen.getByRole("button", { name: "Add provider" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    await screen.findByRole("heading", { name: "Finish signing in" });
    expect(beginLogin).toHaveBeenCalledWith(undefined, "codex");
    expect(screen.queryByRole("button", { name: "Continue to sign in" })).toBeNull();
  });

  it("reserves and navigates the Claude tab only from an explicit sign-in click", async () => {
    const tab = { opener: {}, closed: false, location: { replace: jest.fn() }, close: jest.fn() };
    (window.open as jest.Mock).mockReturnValue(tab);
    (listConnections as jest.Mock).mockResolvedValue([{ ...account, provider: "claude", method: "claude_native" }]);
    (beginLogin as jest.Mock).mockResolvedValue({ progress: { attempt_id: "fixture", provider: "claude", status: "connecting", connection_id: null, code: null }, authorization_url: "https://claude.com/cai/oauth/authorize?state=fixture" });
    render(<ProviderConnections />);
    expect(window.open).not.toHaveBeenCalled();
    fireEvent.click(await screen.findByRole("button", { name: /View connection for/ }));
    fireEvent.click(screen.getByRole("button", { name: "Sign in again" }));
    await screen.findByLabelText("Claude sign-in code");
    expect(window.open).toHaveBeenCalledTimes(1);
    expect(tab.opener).toBeNull();
    expect(tab.location.replace).toHaveBeenCalledWith("https://claude.com/cai/oauth/authorize?state=fixture");
    expect(screen.queryByRole("link", { name: "Continue to Claude" })).toBeNull();
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
    await screen.findByRole("heading", { name: "Connection saved!" });
    expect(window.location.search).toBe("");
    await screen.findByRole("heading", { name: "Providers" }, { timeout: 4000 });
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
    await screen.findByText(/Waiting for sign-in/);
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
    await screen.findByRole("heading", { name: "Connection saved!" });
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
  it("does not present a runner outage as a required new login", async () => {
    (listConnections as jest.Mock).mockResolvedValue([{ ...account, provider: "claude", method: "claude_native", auth_state: "unavailable" }]);
    render(<ProviderConnections />);
    fireEvent.click(await screen.findByRole("button", { name: /Work account/ }));
    expect(screen.getByText("Unavailable")).toBeTruthy();
    expect(screen.getByText("We cannot check this connection right now. Refresh to check again.")).toBeTruthy();
    expect(screen.queryByText("Sign in again to restore access for this account.")).toBeNull();
    expect(beginLogin).not.toHaveBeenCalled();
  });

  it("holds the callback handoff through duplicate completion then returns once to the list", async () => {
    jest.useFakeTimers();
    try {
      const id = "00000000-0000-4000-8000-000000000002";
      window.history.replaceState(null, "", `/settings/providers?attempt=${id}`);
      let finishRead: (value: unknown) => void;
      (listConnections as jest.Mock).mockReturnValue(new Promise(resolve => { finishRead = resolve; }));
      (readProgress as jest.Mock).mockResolvedValue({ attempt_id: id, status: "duplicate", connection_id: account.connection_id, code: null });
      render(<ProviderConnections />);
      expect(screen.getByRole("heading", { name: "Finishing sign-in…" })).toBeTruthy();
      expect(screen.queryByRole("heading", { name: "Providers" })).toBeNull();
      await act(async () => { finishRead!([account]); });
      expect(screen.getByRole("heading", { name: "Already connected" })).toBeTruthy();
      expect(screen.getByText(/Your existing connection is unchanged/)).toBeTruthy();
      act(() => { jest.advanceTimersByTime(2799); });
      expect(screen.queryByRole("heading", { name: "Providers" })).toBeNull();
      act(() => { jest.advanceTimersByTime(1); });
      expect(screen.getByRole("heading", { name: "Providers" })).toBeTruthy();
      expect(screen.getByText("Work account")).toBeTruthy();
      expect(beginLogin).not.toHaveBeenCalled();
      expect(sessionStorage.getItem("laomedo.provider-attempt")).toBeNull();
    } finally { jest.useRealTimers(); }
  });

  it("explains confirmed same-account reauthentication without claiming it was a duplicate", async () => {
    sessionStorage.setItem("laomedo.provider-attempt", "fixture");
    sessionStorage.setItem("laomedo.provider-reconnecting", "true");
    (listConnections as jest.Mock).mockResolvedValue([account]);
    (readProgress as jest.Mock).mockResolvedValue({ attempt_id: "fixture", status: "connected", connection_id: account.connection_id, code: null });
    render(<ProviderConnections />);
    await screen.findByRole("heading", { name: "Connection saved!" });
    expect(screen.getByText("You signed in to the same account again.")).toBeTruthy();
    expect(screen.queryByText("Already connected")).toBeNull();
    expect(sessionStorage.getItem("laomedo.provider-reconnecting")).toBeNull();
  });

  it("leaves the returning state when another tab cancelled its receipt", async () => {
    sessionStorage.setItem("laomedo.provider-attempt", "fixture");
    (readProgress as jest.Mock).mockResolvedValue({ attempt_id: "fixture", status: "cancelled", connection_id: null, code: null });
    render(<ProviderConnections />);
    await screen.findByRole("heading", { name: "Providers" });
    expect(screen.queryByText("Finishing sign-in…")).toBeNull();
    expect(sessionStorage.getItem("laomedo.provider-attempt")).toBeNull();
  });

  it("replaces a failed callback read with recovery and can reconcile the same receipt", async () => {
    sessionStorage.setItem("laomedo.provider-attempt", "fixture");
    (listConnections as jest.Mock).mockRejectedValueOnce(new Error("network failure")).mockResolvedValue([account]);
    (readProgress as jest.Mock).mockResolvedValue({ attempt_id: "fixture", status: "connected", connection_id: account.connection_id, code: null });
    render(<ProviderConnections />);
    await screen.findByRole("heading", { name: "Check connection" });
    expect(screen.queryByText("Finishing sign-in…")).toBeNull();
    expect(screen.getByRole("button", { name: "Try again" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByRole("heading", { name: "Connection saved!" });
    expect(readProgress).toHaveBeenCalledWith("fixture");
    expect(beginLogin).not.toHaveBeenCalled();
  });

  it("ignores unknown login query values without showing an endless handoff", async () => {
    window.history.replaceState(null, "", "/settings/providers?login=unknown");
    render(<ProviderConnections />);
    await screen.findByText("No providers connected");
    expect(screen.getByRole("heading", { name: "Providers" })).toBeTruthy();
  });

  it("offers a fresh connection after an account mismatch without launching sign-in", async () => {
    sessionStorage.setItem("laomedo.provider-attempt", "fixture");
    (listConnections as jest.Mock).mockResolvedValue([account]);
    (readProgress as jest.Mock).mockResolvedValue({ attempt_id: "fixture", provider: "codex", status: "failed", connection_id: account.connection_id, code: "provider_account_mismatch" });
    render(<ProviderConnections />);
    await screen.findByRole("heading", { name: "Different account selected" });
    fireEvent.click(screen.getByRole("button", { name: "Add as new connection" }));
    await screen.findByRole("heading", { name: "Connect Codex" });
    expect(beginLogin).not.toHaveBeenCalled();
    expect(sessionStorage.getItem("laomedo.provider-attempt")).toBeNull();
  });

  it("reconciles an uncertain Go save through the actual list without resubmitting its key", async () => {
    (saveGoConnection as jest.Mock).mockRejectedValue(new ProviderFailure("provider_save_unconfirmed"));
    render(<ProviderConnections />);
    fireEvent.click(await screen.findByRole("button", { name: /Add provider/ }));
    fireEvent.click(screen.getByRole("button", { name: "OpenCode" }));
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    fireEvent.change(screen.getByLabelText("Connection name"), { target: { value: "My Go plan" } });
    fireEvent.change(screen.getByLabelText("OpenCode Go key"), { target: { value: "fixture-go-key" } });
    fireEvent.click(screen.getByRole("button", { name: "Save connection" }));
    await screen.findByRole("heading", { name: "Check connection" });
    expect(screen.getByRole("button", { name: "Try again" })).toBeDisabled();
    (listConnections as jest.Mock).mockResolvedValue([{ ...account, provider: "opencode", method: "opencode_go_key", auth_state: "unavailable" }]);
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await screen.findByRole("heading", { name: "Providers" });
    expect(saveGoConnection).toHaveBeenCalledTimes(1);
    expect(beginLogin).not.toHaveBeenCalled();
  });

  it("reports a failed confirmation reread and discards stale disconnect permission", async () => {
    (listConnections as jest.Mock).mockResolvedValue([account]);
    (inspectDisconnect as jest.Mock).mockResolvedValueOnce({ connection_id: account.connection_id, generation: 1, active_runs: 0, revision: 1 }).mockRejectedValueOnce(new Error("offline"));
    (disconnect as jest.Mock).mockRejectedValue(new ProviderFailure("provider_confirmation_changed"));
    render(<ProviderConnections />);
    fireEvent.click(await screen.findByRole("button", { name: /View connection for/ }));
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    await screen.findByRole("heading", { name: /Disconnect Codex/ });
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    await screen.findByText("Your provider connections could not be checked.");
    expect(screen.queryByRole("heading", { name: /Disconnect Codex/ })).toBeNull();
  });

});
