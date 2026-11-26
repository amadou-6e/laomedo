import { act, render, screen } from "@testing-library/react";
import OpenCodeUsage from "./OpenCodeUsage";
import { readSubscriptionLimits } from "@/components/laomedoProviders/api";
jest.mock("@/components/laomedoProviders/api", () => ({ readSubscriptionLimits: jest.fn() }));
jest.mock("@/modals/graphAgents/components", () => ({ MessageMarkdown: ({text}: {text: string}) => <p>{text}</p> }));
jest.mock("../messages/Message", () => ({ UserMessage: ({text}: {text: string}) => <p>{text}</p> }));
test("usage is a command snapshot with no reload, close or polling controls", async () => {
  jest.useFakeTimers();
  jest.mocked(readSubscriptionLimits).mockResolvedValue({connection_id: "account", generation: 1, state: "ready", reason: null, observed_at: 1, stale_after: 2, snapshot: {submitted_turns: 0, buckets: [{limit_id: "go", label: "OpenCode Go", plan: null, credits: null, windows: [
    {kind: "primary", used_percent: 0, window_minutes: 300, resets_at: null},
    {kind: "secondary", used_percent: 13, window_minutes: 10080, resets_at: null},
    {kind: "monthly", used_percent: 18, window_minutes: null, resets_at: null},
  ]}]}});
  try {
    const view = render(<OpenCodeUsage connection="account" generation={1} />);
    expect(await screen.findByText(/87% remaining/)).toHaveTextContent("100% remaining");
    expect(screen.getByText(/82% remaining/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    await act(async () => { jest.advanceTimersByTime(30000); });
    expect(readSubscriptionLimits).toHaveBeenCalledTimes(1);
    view.unmount();
  } finally { jest.useRealTimers(); }
});
