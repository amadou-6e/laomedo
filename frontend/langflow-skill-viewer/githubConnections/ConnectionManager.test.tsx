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
  navigateToAuthorization,
  ConnectionFailure,
} from "./api";

jest.mock("./api", () => ({
  authorizationUrl: jest.requireActual("./api").authorizationUrl,
  installationUrl: jest.requireActual("./api").installationUrl,
  connectionCapability: jest.fn(),
  connectionRequest: jest.fn(),
  navigateToAuthorization: jest.fn(),
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
            app_slug: "qa",
            mode: "browser",
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
    screen.getByRole("heading", { name: "GitHub sign-in isn't set up" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "Try again" }),
  ).not.toBeInTheDocument();
  expect(screen.queryByLabelText("Client secret")).not.toBeInTheDocument();
  expect(connectionRequest).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByText("Use a personal access token instead"));
  expect(await screen.findByLabelText("Personal access token")).toHaveAttribute(
    "type",
    "password",
  );
});

it("waits for Continue to GitHub before navigating this tab to the exact returned request", async () => {
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
                app_slug: "qa",
                mode: "browser",
                expires_at: 9999999999,
                inventory: null,
                authorization_url:
                  "https://github.com/login/oauth/authorize?client_id=older",
              },
              {
                request_id: "pending",
                connection_id: "new",
                phase: "authorize",
                app_slug: "qa",
                mode: "browser",
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
  const continueButton = await screen.findByRole("button", {
    name: "Continue to GitHub",
  });
  expect(navigateToAuthorization).not.toHaveBeenCalled();
  expect(window.open).not.toHaveBeenCalled();
  fireEvent.click(continueButton);
  expect(connectionRequest).toHaveBeenCalledTimes(2);
  expect(navigateToAuthorization).toHaveBeenLastCalledWith(
    "https://github.com/login/oauth/authorize?client_id=qa",
  );
  expect(navigateToAuthorization).toHaveBeenCalledTimes(1);
  expect(window.open).not.toHaveBeenCalled();
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
    screen.getByRole("button", { name: "Back to connections" }),
  ).toBeVisible();
  expect(
    screen.queryByRole("button", { name: "+ Add connection" }),
  ).not.toBeInTheDocument();
});

it("keeps disconnect reachable for an account needing sign-in without App setup", async () => {
  const connection = {
    id: "stale-account",
    generation: 7,
    mode: "browser",
    state: "reauthorization_required",
    principal: { id: 99, login: "old-account" },
    repositories: [],
  };
  (connectionRequest as jest.Mock).mockImplementation((action?: string) =>
    Promise.resolve({
      index: {
        ...initial,
        app: null,
        connections:
          action === "disconnect"
            ? []
            : [
                {
                  connection,
                  availability: "reauthorization_required",
                  credential_cleanup_pending: false,
                },
              ],
      },
    }),
  );
  render(<ConnectionManager />);
  fireEvent.click(
    await screen.findByRole("button", { name: "View connection" }),
  );
  expect(screen.getByRole("button", { name: "Sign in again" })).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
  await screen.findByRole("heading", { name: "Connection removed" });
  expect(connectionRequest).toHaveBeenCalledWith("disconnect", {
    connection_id: "stale-account",
    generation: 7,
  });
  expect(
    (connectionRequest as jest.Mock).mock.calls.some(
      ([action]) => action === "begin",
    ),
  ).toBe(false);
});

it.each([false, true])(
  "keeps disconnected account cleanup separate from older pending cleanup (%s)",
  async (failed) => {
    const connection = {
      id: "selected",
      generation: 1,
      mode: "browser",
      state: "ready",
      principal: { id: 99, login: "account" },
      repositories: [],
    };
    (connectionRequest as jest.Mock).mockImplementation((action?: string) =>
      Promise.resolve({
        index: {
          ...initial,
          credential_cleanup_pending: true,
          connections: [
            {
              connection: {
                ...connection,
                state: action === "disconnect" ? "revoked" : "ready",
              },
              availability: action === "disconnect" ? "revoked" : "ready",
              credential_cleanup_pending: action === "disconnect" && failed,
            },
          ],
        },
      }),
    );
    render(<ConnectionManager />);
    fireEvent.click(
      await screen.findByRole("button", { name: "View connection" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    await screen.findByRole("heading", {
      name: failed ? "Disconnected" : "Connection removed",
    });
    expect(
      Boolean(screen.queryByRole("button", { name: "Retry cleanup" })),
    ).toBe(failed);
    fireEvent.click(
      screen.getByRole("button", { name: "Back to connections" }),
    );
    fireEvent.click(
      screen.getByRole("button", {
        name: "Some saved sign-in details could not be removed. Retry cleanup",
      }),
    );
    expect(
      screen.getByRole("heading", { name: "Credential cleanup" }),
    ).toBeVisible();
    expect(
      screen.getByText(
        "Some credentials from earlier connections or sign-in attempts still need to be removed.",
      ),
    ).toBeVisible();
  },
);

it("explains an expired sign-in and returns to saved connections without replaying it", async () => {
  window.history.replaceState(
    null,
    "",
    "/settings/github?outcome=signin-expired",
  );
  render(<ConnectionManager />);
  await screen.findByRole("heading", { name: "Connection request expired" });
  expect(
    screen.getByText(
      "This step took too long. Your saved connections have not changed.",
    ),
  ).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Back to connections" }));
  await screen.findByRole("button", { name: "+ Add connection" });
  expect(
    (connectionRequest as jest.Mock).mock.calls.every(
      ([action]) => action === undefined,
    ),
  ).toBe(true);
});

it("treats an expired consent save as a definite refusal, never an uncertain completion", async () => {
  (connectionRequest as jest.Mock).mockImplementation((action?: string) => {
    if (action === "confirm")
      return Promise.reject(
        new ConnectionFailure("github_connection_attempt_expired"),
      );
    return Promise.resolve({
      index: {
        ...initial,
        pending: [
          {
            request_id: "pending",
            connection_id: "new",
            phase: "consent",
            app_slug: "qa",
            mode: "browser",
            expires_at: 9999999999,
            authorization_url: null,
            inventory: {
              principal: { id: 1, login: "account" },
              repositories: [
                { id: 7, full_name: "account/repo", private: true },
              ],
            },
          },
        ],
      },
    });
  });
  render(<ConnectionManager />);
  fireEvent.click(await screen.findByRole("checkbox"));
  fireEvent.click(screen.getByRole("button", { name: "Save access" }));
  await screen.findByRole("heading", { name: "Connection request expired" });
  expect(screen.queryByText(/may still be completing/)).not.toBeInTheDocument();
});

it("checks missing sign-in configuration without starting or replaying authorization", async () => {
  (connectionRequest as jest.Mock).mockResolvedValue({
    index: { ...initial, app: null },
  });
  render(<ConnectionManager />);
  fireEvent.click(
    await screen.findByRole("button", { name: "+ Add connection" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Back to connections" }),
    ).toBeEnabled(),
  );
  expect(
    (connectionRequest as jest.Mock).mock.calls.every(
      ([action]) => action === undefined,
    ),
  ).toBe(true);
  fireEvent.click(screen.getByRole("button", { name: "Back to connections" }));
  expect(
    screen.getByRole("button", { name: "+ Add connection" }),
  ).toBeVisible();
});

it("cleans inactive sign-in details once on entry without retrying failures on polls", async () => {
  (connectionRequest as jest.Mock).mockResolvedValue({
    index: { ...initial, credential_cleanup_pending: true },
  });
  render(<ConnectionManager />);
  await waitFor(() =>
    expect(connectionRequest).toHaveBeenCalledWith("cleanup", {}),
  );
  expect(
    (connectionRequest as jest.Mock).mock.calls.filter(
      ([action]) => action === "cleanup",
    ),
  ).toHaveLength(1);
  expect(
    await screen.findByRole("button", { name: /Some saved sign-in details/ }),
  ).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Refresh" }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: "Refresh" })).toBeEnabled(),
  );
  expect(
    (connectionRequest as jest.Mock).mock.calls.filter(
      ([action]) => action === "cleanup",
    ),
  ).toHaveLength(1);
});

it("does not invalidate another tab when automatically cleaning inactive credentials", async () => {
  const observer = new BrowserChannel("laomedo-private-connections");
  const receive = jest.fn();
  observer.onmessage = receive;
  (connectionRequest as jest.Mock).mockResolvedValue({
    index: { ...initial, credential_cleanup_pending: true },
  });
  render(<ConnectionManager />);
  await waitFor(() =>
    expect(connectionRequest).toHaveBeenCalledWith("cleanup", {}),
  );
  expect(receive).not.toHaveBeenCalled();
});

it("discards an inline token when collapsed without cancelling or navigating", async () => {
  (connectionRequest as jest.Mock).mockResolvedValue({
    index: {
      ...initial,
      pending: [
        {
          request_id: "active",
          connection_id: "new",
          expires_at: 9999999999,
          phase: "authorize",
          app_slug: "qa",
          mode: "browser",
          inventory: null,
          authorization_url:
            "https://github.com/login/oauth/authorize?client_id=qa",
        },
      ],
    },
  });
  render(<ConnectionManager />);
  const toggle = await screen.findByRole("button", {
    name: "Use a personal access token instead",
  });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(toggle);
  const token = screen.getByLabelText("Personal access token");
  expect(token).toHaveAttribute("type", "password");
  fireEvent.change(token, { target: { value: "non-secret-test-value" } });
  fireEvent.click(toggle);
  expect(
    screen.queryByLabelText("Personal access token"),
  ).not.toBeInTheDocument();
  fireEvent.click(toggle);
  expect(screen.getByLabelText("Personal access token")).toHaveValue("");
  expect(navigateToAuthorization).not.toHaveBeenCalled();
  expect(connectionRequest).toHaveBeenCalledTimes(1);
});

it("keeps background waiting checks silent while retaining explicit request progress", async () => {
  let complete!: (value: unknown) => void;
  const waiting = {
    ...initial,
    pending: [
      {
        request_id: "active",
        connection_id: "new",
        expires_at: 9999999999,
        phase: "authorize",
        app_slug: "qa",
        mode: "browser",
        inventory: null,
        authorization_url:
          "https://github.com/login/oauth/authorize?client_id=qa",
      },
    ],
  };
  (connectionRequest as jest.Mock)
    .mockResolvedValueOnce({ index: waiting })
    .mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve;
        }),
    );
  render(<ConnectionManager />);
  await screen.findByRole("button", { name: "Continue to GitHub" });
  act(() => window.dispatchEvent(new Event("focus")));
  await waitFor(() => expect(connectionRequest).toHaveBeenCalledTimes(2));
  expect(screen.queryByText(/Checking/)).not.toBeInTheDocument();
  expect(
    screen.getByRole("heading", { name: "Continue on GitHub" }),
  ).toBeVisible();
  expect(navigateToAuthorization).not.toHaveBeenCalled();
  await act(async () => complete({ index: waiting }));
});

it.each(["matched-browser", "unknown", "token"])(
  "refreshes installation return only for the bound browser consent: %s",
  async (kind) => {
    const observer = new BrowserChannel("laomedo-private-connections");
    const receive = jest.fn();
    observer.onmessage = receive;
    const id = "04c5b5b0-3859-4bf3-999c-08a189be7f06";
    window.history.replaceState(
      null,
      "",
      `/settings/github?setup_action=install&state=${id}&installation_id=123`,
    );
    (connectionRequest as jest.Mock).mockResolvedValue({
      index: {
        ...initial,
        pending: [
          {
            request_id: kind === "unknown" ? "other" : id,
            connection_id: "new",
            expires_at: 9999999999,
            phase: "consent",
            app_slug: "qa",
            mode: kind === "token" ? "token" : "browser",
            authorization_url: null,
            inventory: {
              principal: { id: 1, login: "account" },
              repositories: [],
            },
          },
        ],
      },
    });
    render(<ConnectionManager />);
    if (kind === "unknown")
      await screen.findByRole("button", { name: "+ Add connection" });
    else await screen.findByRole("heading", { name: "Choose repositories" });
    await act(async () => {});
    const refreshes = (connectionRequest as jest.Mock).mock.calls.filter(
      ([action]) => action === "inventory",
    );
    if (kind === "matched-browser")
      expect(refreshes).toEqual([["inventory", { request_id: id }]]);
    else expect(refreshes).toHaveLength(0);
    expect(receive).not.toHaveBeenCalled();
    expect(navigateToAuthorization).not.toHaveBeenCalled();
    expect(window.location.search).toBe("");
  },
);
