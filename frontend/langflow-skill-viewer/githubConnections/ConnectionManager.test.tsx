import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import ConnectionManager from "./ConnectionManager";
import {
  connectionCapability,
  connectionRequest,
  ConnectionFailure,
} from "./api";

jest.mock("./api", () => ({
  authorizationUrl: jest.requireActual("./api").authorizationUrl,
  connectionCapability: jest.fn(),
  connectionRequest: jest.fn(),
  ConnectionFailure: class extends Error {
    constructor(public code: string) {
      super(code);
      Object.setPrototypeOf(this, new.target.prototype);
    }
  },
}));
jest.mock("@/components/ui/button", () => ({
  buttonVariants: () => "button-style",
  Button: ({ children, variant, ...props }: any) => (
    <button {...props}>{children}</button>
  ),
}));
jest.mock("@/components/laomedoProfiles/useProfileSessionActions", () => ({
  __esModule: true,
  default: () => ({ notice: null, busy: false }),
}));
jest.mock("@/components/laomedoErrors/ErrorExplanation", () => ({
  __esModule: true,
  default: () => <div>Error notice</div>,
}));

class BrowserChannel {
  static channels: BrowserChannel[] = [];
  onmessage: ((event: { data: any }) => void) | null = null;
  closed = false;
  constructor(public name: string) {
    BrowserChannel.channels.push(this);
  }
  postMessage(data: any) {
    // Real browser semantics: another object in this SAME document receives it.
    for (const channel of BrowserChannel.channels) {
      if (channel !== this && !channel.closed && channel.name === this.name)
        channel.onmessage?.({ data });
    }
  }
  close() {
    this.closed = true;
  }
}

const initial = {
  revision: 1,
  callback_uri:
    "http://127.0.0.1:17867/api/v1/laomedo/github-connections/callback",
  app: { slug: "qa", client_id: "qa" },
  connections: [],
  pending: [],
  credential_cleanup_pending: false,
};

beforeEach(() => {
  jest.clearAllMocks();
  window.history.replaceState(null, "", "/settings/github");
  jest.spyOn(window, "open").mockReturnValue(null);
  BrowserChannel.channels = [];
  Object.defineProperty(globalThis, "BroadcastChannel", {
    configurable: true,
    writable: true,
    value: BrowserChannel,
  });
  Object.defineProperty(crypto, "randomUUID", {
    configurable: true,
    value: () => "this-manager",
  });
  (connectionCapability as jest.Mock).mockResolvedValue(true);
  (connectionRequest as jest.Mock).mockResolvedValue({ index: initial });
});

it("keeps its initiating mutation busy and displays the response despite same-document broadcasts", async () => {
  let complete!: (value: unknown) => void;
  const mutation = new Promise((resolve) => {
    complete = resolve;
  });
  (connectionRequest as jest.Mock).mockImplementation((action?: string) =>
    action ? mutation : Promise.resolve({ index: initial }),
  );
  render(<ConnectionManager />);
  fireEvent.click(
    await screen.findByRole("button", { name: "+ Add connection" }),
  );
  expect(screen.getByRole("button", { name: "Refresh" })).toBeDisabled();
  expect(screen.queryByText(/changed in another tab/)).not.toBeInTheDocument();
  await act(async () =>
    complete({
      index: {
        ...initial,
        revision: 2,
        pending: [
          {
            request_id: "pending",
            connection_id: "connection",
            expires_at: 1,
            phase: "authorize",
            inventory: null,
            authorization_url:
              "https://github.com/login/oauth/authorize?client_id=qa",
          },
        ],
      },
    }),
  );
  expect(
    await screen.findByRole("button", { name: "Open GitHub again" }),
  ).toBeEnabled();
  expect(connectionRequest).toHaveBeenCalledWith("begin", {});
});

it("invalidates an in-flight result from another document without restoring stale state", async () => {
  let complete!: (value: unknown) => void;
  const mutation = new Promise((resolve) => {
    complete = resolve;
  });
  (connectionRequest as jest.Mock).mockImplementation((action?: string) =>
    action ? mutation : Promise.resolve({ index: initial }),
  );
  render(<ConnectionManager />);
  fireEvent.click(
    await screen.findByRole("button", { name: "+ Add connection" }),
  );
  act(() => {
    const other = new BrowserChannel("laomedo-private-connections");
    other.postMessage({ type: "invalidate", source: "another-document" });
    other.close();
  });
  await act(async () => complete({ index: initial }));
  await waitFor(() =>
    expect(screen.getByText(/changed in another tab/)).toBeVisible(),
  );
  expect(
    screen.getByRole("button", { name: "+ Add connection" }),
  ).toBeDisabled();
  expect(
    screen.queryByRole("button", { name: "Open GitHub again" }),
  ).not.toBeInTheDocument();
});

it.each([
  "github_connection_input_invalid",
  "github_token_unsupported",
  "private_request_refused",
  "github_connection_unavailable",
  "private_session_required",
])(
  "distinguishes definite refusal from an uncertain mutation outcome: %s",
  async (code) => {
    (connectionRequest as jest.Mock).mockImplementation((action?: string) =>
      action
        ? Promise.reject(new ConnectionFailure(code))
        : Promise.resolve({ index: initial }),
    );
    render(<ConnectionManager />);
    fireEvent.click(
      await screen.findByRole("button", { name: "+ Add connection" }),
    );
    await screen.findByRole("alert");
    const uncertain = screen.queryByText(/The request may still be completing/);
    if (
      ["github_connection_unavailable", "private_session_required"].includes(
        code,
      )
    )
      expect(uncertain).toBeVisible();
    else expect(uncertain).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "+ Add connection" }),
    ).not.toBeInTheDocument();
  },
);

it("shows unavailable sign-in without requiring app credentials", async () => {
  (connectionRequest as jest.Mock).mockResolvedValue({
    index: { ...initial, app: null },
  });
  render(<ConnectionManager />);
  fireEvent.click(
    await screen.findByRole("button", { name: "+ Add connection" }),
  );
  expect(
    screen.getByRole("heading", { name: "GitHub is unavailable" }),
  ).toBeVisible();
  expect(screen.queryByLabelText("Client secret")).not.toBeInTheDocument();
  expect(connectionRequest).toHaveBeenCalledTimes(1);
  fireEvent.click(
    screen.getByRole("button", {
      name: "Advanced: use a personal access token",
    }),
  );
  expect(screen.getByLabelText("Personal access token")).toHaveAttribute(
    "type",
    "password",
  );
});

it("opens the returned authorization URL automatically in the reserved browser tab", async () => {
  const replace = jest.fn();
  jest.spyOn(window, "open").mockReturnValue({
    opener: null,
    closed: false,
    close: jest.fn(),
    location: { replace },
  } as any);
  (connectionRequest as jest.Mock).mockImplementation((action?: string) =>
    Promise.resolve({
      outcome: action ? { request_id: "pending" } : null,
      index: action
        ? {
            ...initial,
            pending: [
              {
                request_id: "older",
                connection_id: "older-account",
                phase: "authorize",
                expires_at: 9999999999,
                inventory: null,
                authorization_url:
                  "https://github.com/login/oauth/authorize?client_id=older",
              },
              {
                request_id: "pending",
                connection_id: "new",
                phase: "authorize",
                expires_at: 9999999999,
                inventory: null,
                authorization_url:
                  "https://github.com/login/oauth/authorize?client_id=qa",
              },
            ],
          }
        : initial,
    }),
  );
  render(<ConnectionManager />);
  fireEvent.click(
    await screen.findByRole("button", { name: "+ Add connection" }),
  );
  await waitFor(() =>
    expect(replace).toHaveBeenCalledWith(
      "https://github.com/login/oauth/authorize?client_id=qa",
    ),
  );
  fireEvent.click(screen.getByRole("button", { name: "Open GitHub again" }));
  expect(connectionRequest).toHaveBeenCalledTimes(2);
  expect(window.open).toHaveBeenLastCalledWith(
    "https://github.com/login/oauth/authorize?client_id=qa",
    "_blank",
    "noopener,noreferrer",
  );
});

it("edits repository consent using the selected saved account without beginning a new login", async () => {
  (connectionRequest as jest.Mock).mockResolvedValue({
    index: {
      ...initial,
      connections: [
        {
          connection: {
            id: "saved",
            generation: 1,
            mode: "browser",
            state: "ready",
            principal: { id: 1, login: "qa" },
            repositories: [],
          },
          availability: "ready",
          credential_cleanup_pending: false,
        },
      ],
    },
  });
  render(<ConnectionManager />);
  fireEvent.click(
    await screen.findByRole("button", { name: "View connection" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Change repositories" }));
  await waitFor(() =>
    expect(connectionRequest).toHaveBeenCalledWith("edit", {
      connection_id: "saved",
    }),
  );
});

it("keeps an unconfirmed callback visible after initial state reconciliation", async () => {
  window.history.replaceState(
    null,
    "",
    "/settings/github?outcome=authorization-unconfirmed",
  );
  render(<ConnectionManager />);
  await screen.findByRole("alert");
  expect(window.location.search).toBe("");
  expect(
    screen.getByRole("button", { name: "Check current state" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "+ Add connection" }),
  ).not.toBeInTheDocument();
});
