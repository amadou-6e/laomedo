import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import ConnectionRegistration from "./ConnectionRegistration";
import { connectionRequest } from "./api";

jest.mock("./api", () => ({ connectionRequest: jest.fn() }));
jest.mock("@/components/ui/button", () => ({
  Button: ({ children, asChild, ignoreTitleCase, ...props }: any) =>
    asChild ? children : <button {...props}>{children}</button>,
}));

beforeEach(() => {
  jest.clearAllMocks();
  window.history.replaceState(null, "", "/settings/github");
});

test("registration posts the server manifest directly to GitHub, without another window", async () => {
  const submit = jest
    .spyOn(HTMLFormElement.prototype, "submit")
    .mockImplementation(function (this: HTMLFormElement) {
      expect(this.action).toBe(
        "https://github.com/settings/apps/new?state=synthetic",
      );
      expect(this.method).toBe("post");
      expect(new FormData(this).get("manifest")).toBe(
        JSON.stringify({ public: false }),
      );
    });
  (connectionRequest as jest.Mock).mockResolvedValue({
    outcome: {
      action: "https://github.com/settings/apps/new?state=synthetic",
      manifest: { public: false },
    },
  });
  render(<ConnectionRegistration close={jest.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Continue to GitHub" }));
  await waitFor(() => expect(submit).toHaveBeenCalledTimes(1));
  expect(connectionRequest).toHaveBeenCalledWith("provision");
  submit.mockRestore();
});

test("an unexpected registration destination is refused and never submitted", async () => {
  const submit = jest
    .spyOn(HTMLFormElement.prototype, "submit")
    .mockImplementation(() => {});
  (connectionRequest as jest.Mock).mockResolvedValue({
    outcome: { action: "https://example.org/settings/apps/new", manifest: {} },
  });
  render(<ConnectionRegistration close={jest.fn()} />);
  fireEvent.click(screen.getByRole("button", { name: "Continue to GitHub" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Setup could not be confirmed",
  );
  expect(submit).not.toHaveBeenCalled();
  submit.mockRestore();
});

test("leaving registration prevents a late response from navigating", async () => {
  let resolve: (value: unknown) => void = () => {};
  (connectionRequest as jest.Mock).mockReturnValue(
    new Promise((done) => {
      resolve = done;
    }),
  );
  const submit = jest
    .spyOn(HTMLFormElement.prototype, "submit")
    .mockImplementation(() => {});
  const { unmount } = render(<ConnectionRegistration close={jest.fn()} />);
  expect(connectionRequest).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "Continue to GitHub" }));
  unmount();
  resolve({
    outcome: {
      action: "https://github.com/settings/apps/new?state=synthetic",
      manifest: { public: false },
    },
  });
  await waitFor(() => expect(connectionRequest).toHaveBeenCalledTimes(1));
  expect(submit).not.toHaveBeenCalled();
  submit.mockRestore();
});
