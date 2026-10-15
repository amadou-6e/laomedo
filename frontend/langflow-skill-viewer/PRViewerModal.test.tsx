import React from "react";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import PRViewerModal, { prSelection } from "./index";
import { api } from "@/controllers/API/api";

jest.unmock("react-markdown");

jest.mock("@/controllers/API/api", () => ({ api: { post: jest.fn() } }));
jest.mock("@/customization/utils/urls", () => ({ getBaseUrl: () => "/api/v1/" }));
jest.mock("@/modals/baseModal", () => {
  const Modal = ({ open, children }: any) => open ? <div role="dialog">{children}</div> : null;
  Modal.Header = ({ children }: any) => <header>{children}</header>;
  Modal.Content = ({ children }: any) => <main>{children}</main>;
  return { __esModule: true, default: Modal };
});

const template = (number = 1) => ({ repository_url: { value: "https://github.com/owner/repo" },
  pr_choice: { value: `#${number} Change` }, labels: { value: [] }, state: { value: "open" } });
const snapshot = (number = 1) => ({ data: { schema_version: "laomedo.pr-inspection.v1", fetched_at: "now",
  pr: { number, url: `https://github.com/owner/repo/pull/${number}`, title: `Change ${number}`,
    body: "**Rendered markdown**\n<img src='https://external.invalid/image'>\n<script>window.injected=true</script>\n![remote](https://external.invalid/image)\n[unsafe](javascript:alert(1))",
    labels: ["research"], state: "open", draft: true, merged: false,
    head: { branch: "demo", sha: "a".repeat(40) }, base: "main", updated_at: "before" } } });
const post = api.post as jest.Mock;
beforeEach(() => post.mockReset());

test("selection constructs only an exact safe GitHub PR URL", () => {
  expect(prSelection(template()).url).toBe("https://github.com/owner/repo/pull/1");
  expect(prSelection({ ...template(), repository_url: { value: "https://github.com/owner/repo?token=secret" } }).url).toBe("");
  expect(prSelection({ ...template(), pr_choice: { value: "#9007199254740992 Unsafe" } }).url).toBe("");
});

test("viewer reads without an operation, renders safe Markdown and links the selected PR", async () => {
  post.mockResolvedValue(snapshot());
  const { container } = render(<PRViewerModal template={template()} open setOpen={() => {}} />);
  await screen.findByTestId("pr-viewer-content");
  expect(post.mock.calls[0][0]).toBe("/api/v1/laomedo/github-prs/inspect");
  expect(post.mock.calls[0][1]).toEqual({ repository_url: "https://github.com/owner/repo", pr_number: 1, labels: [], state: "open" });
  expect(container.querySelector("strong")?.textContent).toBe("Rendered markdown");
  expect(container.querySelectorAll("img, script")).toHaveLength(0);
  expect(container.querySelector('a[href^="javascript:"]')).toBeNull();
  const link = screen.getByTestId("pr-open-browser");
  expect(link.getAttribute("href")).toBe("https://github.com/owner/repo/pull/1");
  expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  expect(link.getAttribute("target")).toBe("_blank");
  expect(container.textContent).toContain("demo");
  fireEvent.click(screen.getByRole("button", { name: "Refresh PR" }));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
});

test("late responses from an old selection cannot replace current content", async () => {
  let resolveOld: (value: unknown) => void = () => {};
  post.mockImplementationOnce(() => new Promise(resolve => { resolveOld = resolve; })).mockResolvedValueOnce(snapshot(2));
  const { rerender } = render(<PRViewerModal template={template()} open setOpen={() => {}} />);
  rerender(<PRViewerModal template={template(2)} open setOpen={() => {}} />);
  await screen.findByText("#2 Change 2");
  expect(post.mock.calls[0][2].signal.aborted).toBe(true);
  await act(async () => resolveOld(snapshot(1)));
  expect(screen.queryByText("#1 Change 1")).toBeNull();
  expect(screen.getByText("#2 Change 2")).toBeTruthy();
});

test("missing picker identity has no read and no external link", () => {
  render(<PRViewerModal template={{}} open setOpen={() => {}} />);
  expect(screen.getByText("Select a PR first.")).toBeTruthy();
  expect(screen.queryByTestId("pr-open-browser")).toBeNull();
  expect(post).not.toHaveBeenCalled();
});

test("refused reads expose a fixed error and closing aborts the request", async () => {
  post.mockRejectedValue(Error("private-provider-token"));
  const { rerender } = render(<PRViewerModal template={template()} open setOpen={() => {}} />);
  await screen.findByRole("alert");
  expect(screen.getByRole("alert").textContent).not.toContain("private-provider-token");
  rerender(<PRViewerModal template={template()} open={false} setOpen={() => {}} />);
  expect(post.mock.calls[0][2].signal.aborted).toBe(true);
});
