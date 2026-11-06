// Internal presentation controls; not live GitHub acceptance evidence.
import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import GitHubInspectionError, { describeGitHubInspectionFailure } from "./InspectionError";
import IssueViewerModal from "../issues/IssueViewerModal";
import PRViewerModal from "../pull_requests/PRViewerModal";
import { api } from "@/controllers/API/api";
jest.mock("@/controllers/API/api", () => ({ api: { post: jest.fn() } }));
jest.mock("@/customization/utils/urls", () => ({ getBaseUrl: () => "/api/v1/" }));
jest.mock("@/modals/baseModal", () => {
  const Modal = ({ open, children }: any) => open ? <div role="dialog">{children}</div> : null;
  Modal.Header = ({ children }: any) => <header>{children}</header>;
  Modal.Content = ({ children }: any) => <main>{children}</main>;
  return { __esModule: true, default: Modal };
});
const post = api.post as jest.Mock;
const copy = jest.fn().mockResolvedValue(undefined);
beforeEach(() => { post.mockReset(); copy.mockClear(); Object.defineProperty(navigator, "clipboard", { value: { writeText: copy }, configurable: true }); });
const cases = [
  { kind: "issue" as const, Viewer: IssueViewerModal, choice: "issue_choice", label: "issue", suffix: "issues" },
  { kind: "pr" as const, Viewer: PRViewerModal, choice: "pr_choice", label: "PR", suffix: "pull" },
];
test.each(cases)("$kind viewer keeps known failure codes copyable and refreshes only its selected read", async ({ kind, Viewer, choice, label, suffix }) => {
  post.mockRejectedValueOnce({ response: { data: { detail: { code: "github_http_403", private: "do-not-copy" } } } });
  const template = { repository_url: { value: "https://github.com/owner/repo" }, [choice]: { value: "#1 Current" } };
  render(<Viewer template={template} open setOpen={() => {}} />);
  expect(await screen.findByRole("alert")).toHaveTextContent("GitHub refused this request");
  expect(screen.getByRole("alert")).toHaveTextContent("github_http_403");
  fireEvent.click(screen.getByRole("button", { name: "Copy error" }));
  await waitFor(() => expect(copy).toHaveBeenCalled());
  expect(copy.mock.calls[0][0]).toContain("github_http_403");
  expect(copy.mock.calls[0][0]).not.toContain("do-not-copy");
  const resource = { number: 1, url: `https://github.com/owner/repo/${suffix}/1`, title: "Current", body: "Actual-shaped internal control", labels: [], state: "open", updated_at: "before", head: { branch: "topic", sha: "a".repeat(40) }, base: "main", draft: false, merged: false };
  post.mockResolvedValueOnce({ data: { schema_version: `laomedo.${kind}-inspection.v1`, [kind]: resource, fetched_at: "now" } });
  fireEvent.click(screen.getByRole("button", { name: `Refresh ${label}` }));
  await screen.findByTestId(`${kind}-viewer-content`);
  expect(post).toHaveBeenCalledTimes(2);
  for (const [, body] of post.mock.calls) {
    expect(body).not.toHaveProperty("operation");
    expect(body[`${kind === "issue" ? "issue" : "pr"}_number`]).toBe(1);
  }
});
test.each(cases)("$kind missing selection has a descriptive coded refusal and no request", ({ kind, Viewer }) => {
  render(<Viewer template={{}} open setOpen={() => {}} />);
  expect(screen.getByRole("alert")).toHaveTextContent(`selected_${kind}_required`);
  expect(post).not.toHaveBeenCalled();
});
test.each(["issue", "pr"] as const)("%s unknown read failure has a read-only explanation and preserves a safe machine code", kind => {
  const failure = describeGitHubInspectionFailure({ response: { data: { code: "unfamiliar_read_failure" } } }, kind);
  render(<GitHubInspectionError failure={failure} />);
  expect(screen.getByRole("alert")).toHaveTextContent("could not be loaded");
  expect(screen.getByRole("alert")).toHaveTextContent("unfamiliar_read_failure");
  expect(screen.getByRole("alert")).toHaveTextContent("repeats only this read");
});
test.each(["sk_", "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_"])("credential-shaped %s is absent from DOM and copy", prefix => {
  const secret = prefix + "a".repeat(36);
  const failure = describeGitHubInspectionFailure({ response: { data: { detail: { code: secret, trace: secret } } } }, "pr");
  render(<GitHubInspectionError failure={failure} />);
  expect(screen.getByRole("alert")).not.toHaveTextContent(secret);
  expect(JSON.stringify(failure)).not.toContain(secret);
});
