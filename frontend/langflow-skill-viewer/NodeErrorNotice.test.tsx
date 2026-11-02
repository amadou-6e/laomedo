import { render, screen, fireEvent } from "@testing-library/react";
import NodeErrorNotice from "./NodeErrorNotice";
jest.mock("@/controllers/API/api", () => ({ api: { get: jest.fn().mockResolvedValue({ data: { state: "unmanaged", can_start: false } }), post: jest.fn() } }));
jest.mock("@/customization/utils/urls", () => ({ getBaseUrl: () => "/api/v1/" }));
test("node details open the shared card and can be dismissed", () => {
 render(<NodeErrorNotice message="prior_run_required" context={{nodeId:"agent",operation:"resume"}} />);
 expect(screen.queryByRole("region",{name:"Error details"})).toBeNull();
 fireEvent.click(screen.getByRole("button",{name:/Error details:/}));
 expect(screen.getByRole("heading",{name:"No previous run is available"})).toBeVisible();
 fireEvent.click(screen.getByRole("button",{name:"Dismiss"}));
 expect(screen.queryByRole("region",{name:"Error details"})).toBeNull();
});
test("transport details open recovery through the same card frame", async () => {
 render(<NodeErrorNotice message="runner_transport_failed" context={{}} />);
 fireEvent.click(screen.getByRole("button",{name:/Error details:/}));
 await screen.findByRole("region",{name:"Local backend recovery"});
});

test("a refused PR feedback operation opens descriptive, dismissible details", () => {
 const status = {data: {outputs: {task: {message: JSON.stringify({schema_version: "laomedo.github-pr.v1", operation: {status: "failed", error_category: "pr_grant_unavailable"}})}}}};
 render(<NodeErrorNotice status={status} context={{nodeId: "pr",nodeType: "LaomedoGitHubPR"}} />);
 fireEvent.click(screen.getByRole("button",{name:"Error details: This PR operation is not authorized"}));
 expect(screen.getByRole("heading",{name:"This PR operation is not authorized"})).toBeVisible();
 fireEvent.click(screen.getByRole("button",{name:"Dismiss"}));
 expect(screen.queryByRole("region",{name:"Error details"})).toBeNull();
});

jest.mock("@/components/ui/button", () => ({ Button: ({ size, ...props }: any) => <button {...props} /> }));
