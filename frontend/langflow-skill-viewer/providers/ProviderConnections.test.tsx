import { StrictMode } from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ProviderConnections from "./ProviderConnections";
import { beginLogin, listConnections, readProgress } from "./api";

jest.mock("@/components/ui/button", () => ({
  Button: ({ ignoreTitleCase, variant, children, ...props }) => <button {...props}>{children}</button>,
}));
jest.mock("./api", () => ({ beginLogin: jest.fn(), cancelLogin: jest.fn(), listConnections: jest.fn(), readProgress: jest.fn() }));

describe("saved provider Settings", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    sessionStorage.clear();
    window.history.replaceState(null, "", "/settings/providers");
    (listConnections as jest.Mock).mockResolvedValue([]);
  });

  it("loads under StrictMode without starting native sign-in", async () => {
    render(<StrictMode><ProviderConnections /></StrictMode>);
    await screen.findByText("No providers connected");
    expect(beginLogin).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
    await waitFor(() => expect(listConnections).toHaveBeenCalledTimes(3));
    expect(beginLogin).not.toHaveBeenCalled();
  });

  it("chooses type and method before an explicit sign-in action", async () => {
    render(<ProviderConnections />);
    await screen.findByText("No providers connected");
    fireEvent.click(screen.getByRole("button", { name: "Add provider" }));
    expect(screen.getByRole("button", { name: /Claude/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /OpenCode/ })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(screen.getByText("Sign in with ChatGPT")).toBeTruthy();
    expect(beginLogin).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Back to connections" }).querySelector("svg")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Back to connections" }));
    expect(screen.getByRole("heading", { name: "Add provider" })).toBeTruthy();
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
});
