import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import SubscriptionLimits from "./SubscriptionLimits";
import {
  ProviderFailure,
  readSubscriptionLimits,
  type ProviderConnection,
  type SubscriptionObservation,
} from "./api";

jest.mock("@/components/ui/button", () => ({
  Button: ({ variant, size, children, ...props }) => (
    <button {...props}>{children}</button>
  ),
}));
jest.mock("./api", () => ({
  ...jest.requireActual("./api"),
  readSubscriptionLimits: jest.fn(),
}));

const account: ProviderConnection = {
  connection_id: "00000000-0000-4000-8000-000000000001",
  provider: "codex",
  method: "chatgpt_plan_oauth",
  label: "Personal Codex",
  generation: 1,
  lifecycle: "connected",
  auth_state: "ready",
};
const empty: SubscriptionObservation = {
  connection_id: account.connection_id,
  generation: 1,
  state: "not_checked",
  reason: null,
  observed_at: null,
  stale_after: null,
  snapshot: null,
};
const ready: SubscriptionObservation = {
  ...empty,
  state: "ready",
  observed_at: Date.now() / 1000,
  stale_after: Date.now() / 1000 + 60,
  snapshot: {
    submitted_turns: 0,
    buckets: [
      {
        limit_id: "codex",
        label: "Codex",
        plan: null,
        windows: [
          {
            kind: "primary",
            used_percent: 25,
            window_minutes: 300,
            resets_at: 1900000000,
          },
        ],
        credits: { has_credits: true, unlimited: false, balance: "10.25" },
      },
      {
        limit_id: "review",
        label: "Review",
        plan: null,
        windows: [
          {
            kind: "secondary",
            used_percent: 110,
            window_minutes: 10080,
            resets_at: null,
          },
        ],
        credits: null,
      },
    ],
  },
};

beforeEach(() => {
  jest.clearAllMocks();
  (readSubscriptionLimits as jest.Mock).mockResolvedValue(empty);
});

afterEach(() => jest.useRealTimers());

test("mount reads cache only; explicit refresh renders native buckets, over-limit and separate credits", async () => {
  render(<SubscriptionLimits flowId="graph-one" accounts={[account]} />);
  await screen.findByText("Not checked");
  expect(readSubscriptionLimits).toHaveBeenCalledTimes(1);
  expect((readSubscriptionLimits as jest.Mock).mock.calls[0][3].refresh).toBe(
    false,
  );
  (readSubscriptionLimits as jest.Mock).mockResolvedValueOnce(ready);
  fireEvent.click(
    screen.getByRole("button", { name: "Refresh limits for Personal Codex" }),
  );
  await screen.findByText("75% remaining");
  expect(screen.getByText("0% remaining")).toBeInTheDocument();
  expect(screen.getByText("5-hour window")).toBeInTheDocument();
  expect(screen.getByText("7-day window")).toBeInTheDocument();
  expect(screen.getByText("Credit balance: 10.25")).toBeInTheDocument();
  expect(screen.getAllByRole("meter")).toHaveLength(2);
  expect((readSubscriptionLimits as jest.Mock).mock.calls[1][3].refresh).toBe(
    true,
  );
});

test("unknown percentages and reset timestamps stay unknown rather than zero", async () => {
  (readSubscriptionLimits as jest.Mock).mockResolvedValue({
    ...ready,
    snapshot: {
      submitted_turns: 0,
      buckets: [
        {
          limit_id: "codex",
          label: null,
          plan: null,
          credits: null,
          windows: [
            {
              kind: "primary",
              used_percent: null,
              window_minutes: null,
              resets_at: null,
            },
          ],
        },
      ],
    },
  });
  render(<SubscriptionLimits flowId="graph-one" accounts={[account]} />);
  await screen.findByText("Allowance unknown");
  expect(screen.getByText("Reset time unknown")).toBeInTheDocument();
  expect(screen.queryByRole("meter")).not.toBeInTheDocument();
});

test("unsupported providers never request quota or expose an enabled refresh", () => {
  render(
    <SubscriptionLimits
      flowId="graph-one"
      accounts={[{ ...account, provider: "opencode" }]}
    />,
  );
  expect(screen.getByText("Not available")).toBeInTheDocument();
  expect(readSubscriptionLimits).not.toHaveBeenCalled();
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

test("failed refresh keeps only last-known same-account values visibly stale", async () => {
  (readSubscriptionLimits as jest.Mock)
    .mockResolvedValueOnce(ready)
    .mockRejectedValueOnce(new Error("network failure"));
  render(<SubscriptionLimits flowId="graph-one" accounts={[account]} />);
  await screen.findByText("75% remaining");
  fireEvent.click(screen.getByRole("button", { name: /Refresh limits/ }));
  await screen.findByRole("alert");
  expect(screen.getByText("Out of date")).toBeInTheDocument();
  expect(screen.getByText("75% remaining")).toBeInTheDocument();
});

test("revoked or changed generation clears the old quota rather than retaining stale private data", async () => {
  (readSubscriptionLimits as jest.Mock)
    .mockResolvedValueOnce(ready)
    .mockRejectedValueOnce(new ProviderFailure("provider_connection_changed"));
  render(<SubscriptionLimits flowId="graph-one" accounts={[account]} />);
  await screen.findByText("75% remaining");
  fireEvent.click(screen.getByRole("button", { name: /Refresh limits/ }));
  await screen.findByRole("alert");
  expect(screen.queryByText("75% remaining")).not.toBeInTheDocument();
});

test("late account results cannot appear after account and graph selection changes", async () => {
  let finish: (value: SubscriptionObservation) => void = () => {};
  (readSubscriptionLimits as jest.Mock).mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const view = render(
    <SubscriptionLimits flowId="graph-one" accounts={[account]} />,
  );
  const other = {
    ...account,
    connection_id: "00000000-0000-4000-8000-000000000002",
    label: "Work Codex",
  };
  (readSubscriptionLimits as jest.Mock).mockResolvedValue({
    ...empty,
    connection_id: other.connection_id,
  });
  view.rerender(<SubscriptionLimits flowId="graph-two" accounts={[other]} />);
  await screen.findByText("Not checked");
  await act(async () => {
    finish(ready);
  });
  expect(screen.getByText("Work Codex")).toBeInTheDocument();
  expect(screen.queryByText("75% remaining")).not.toBeInTheDocument();
});

test("late old-generation results cannot appear on a reconnected account", async () => {
  let finish: (value: SubscriptionObservation) => void = () => {};
  (readSubscriptionLimits as jest.Mock).mockReturnValueOnce(
    new Promise((resolve) => {
      finish = resolve;
    }),
  );
  const view = render(
    <SubscriptionLimits flowId="graph-one" accounts={[account]} />,
  );
  (readSubscriptionLimits as jest.Mock).mockResolvedValue({
    ...empty,
    generation: 2,
  });
  view.rerender(
    <SubscriptionLimits
      flowId="graph-one"
      accounts={[{ ...account, generation: 2 }]}
    />,
  );
  await screen.findByText("Not checked");
  await act(async () => {
    finish(ready);
  });
  expect(screen.queryByText("75% remaining")).not.toBeInTheDocument();
});

test("age marks cached values stale without an automatic native refresh", async () => {
  jest.useFakeTimers();
  (readSubscriptionLimits as jest.Mock).mockResolvedValue({
    ...ready,
    stale_after: Date.now() / 1000 + 1,
  });
  render(<SubscriptionLimits flowId="graph-one" accounts={[account]} />);
  await act(async () => {});
  expect(screen.getByText("75% remaining")).toBeInTheDocument();
  act(() => {
    jest.advanceTimersByTime(15000);
  });
  expect(screen.getByText("Out of date")).toBeInTheDocument();
  expect(readSubscriptionLimits).toHaveBeenCalledTimes(1);
});
