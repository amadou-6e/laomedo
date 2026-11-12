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
    await screen.findByRole("button", { name: "Connect GitHub" }),
  );
  expect(
    screen.getByRole("button", { name: "Refresh" }),
  ).toBeDisabled();
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
    await screen.findByRole("button", { name: "Continue to GitHub" }),
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
    await screen.findByRole("button", { name: "Connect GitHub" }),
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
    screen.queryByRole("button", { name: "Connect GitHub" }),
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
      await screen.findByRole("button", { name: "Connect GitHub" }),
    );
    await screen.findByText("Error notice");
    const uncertain = screen.queryByText(/The request may still be completing/);
    if (
      ["github_connection_unavailable", "private_session_required"].includes(
        code,
      )
    )
      expect(uncertain).toBeVisible();
    else expect(uncertain).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Connect GitHub" }),
    ).not.toBeInTheDocument();
  },
);
