import { render, screen } from "@testing-library/react";
import { ProtectedRoute } from "@/components/authorization/authGuard";

jest.mock("@/stores/authStore", () => ({__esModule:true,default:(select:any)=>select({isAuthenticated:false,autoLogin:false})}));
jest.mock("@/controllers/API/queries/auth", () => ({useRefreshAccessToken:()=>({mutate:jest.fn()})}));
jest.mock("@/customization/components/custom-navigate", () => ({CustomNavigate:({to}:any)=><a href={to}>Continue login</a>}));

afterEach(()=>window.history.replaceState({},"","/"));

test.each([
  "/assistant?conversation=chat-id&linked=earlier-id",
  "/assistant?conversation=chat-id#message-3",
  "/flow/graph-id?view=activity&node=agent",
])("preserves the full same-site return location through login: %s", destination=>{
  window.history.replaceState({},"",destination);
  render(<ProtectedRoute><p>Private view</p></ProtectedRoute>);
  const login=new URL(screen.getByRole("link",{name:"Continue login"}).getAttribute("href")!,window.location.origin);
  expect(login.pathname).toBe("/login");
  expect(login.searchParams.get("redirect")).toBe(destination);
  expect([...login.searchParams.keys()]).toEqual(["redirect"]);
  expect(screen.queryByText("Private view")).toBeNull();
});
