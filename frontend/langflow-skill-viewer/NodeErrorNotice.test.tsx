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

test("the source error line itself opens shared recovery and safe technical details", () => {
 render(<NodeErrorNotice label="Discovery failed. Check source access and refresh." message="source_discovery_failed" context={{nodeId:"skill",nodeType:"LaomedoSkill"}} />);
 const line=screen.getByRole("button",{name:"Error details: The Skill source could not be loaded"});
 expect(line).toHaveTextContent("Discovery failed. Check source access and refresh.");
 expect(screen.queryByText("Error details", {exact:true})).toBeNull();
 fireEvent.click(line);
 expect(screen.getByRole("heading",{name:"The Skill source could not be loaded"})).toBeVisible();
 expect(screen.getByRole("region",{name:"Error details"})).toHaveTextContent("local checkout");
 fireEvent.click(screen.getByText("Technical details",{exact:true}));
 expect(screen.getByRole("region",{name:"Error details"})).toHaveTextContent("source_discovery_failed");
 fireEvent.click(screen.getByRole("button",{name:"Dismiss"}));
 expect(screen.queryByRole("region",{name:"Error details"})).toBeNull();
});
test("transport details open recovery through the same card frame", async () => {
 render(<NodeErrorNotice message="runner_transport_failed" context={{}} />);
 fireEvent.click(screen.getByRole("button",{name:/Error details:/}));
 await screen.findByRole("region",{name:"Local backend recovery"});
});

jest.mock("@/components/ui/button", () => ({ Button: ({ size, ...props }: any) => <button {...props} /> }));
