import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import GraphPermissions from "./GraphPermissions";
import { assistantRequest } from "../api";
jest.mock("../api", () => ({ assistantRequest: jest.fn() }));
it("revokes only the selected conversation category without running anything", async () => {
  jest.mocked(assistantRequest).mockResolvedValue({ state: "revoked" });
  const onChange = jest.fn();
  render(
    <GraphPermissions
      conversation="chat"
      permissions={["edit", "run"]}
      onChange={onChange}
      onFailure={() => {}}
    />,
  );
  expect(assistantRequest).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole("button", { name: "Ask every time for edit" }),
  );
  await waitFor(() => expect(onChange).toHaveBeenCalledTimes(1));
  expect(assistantRequest).toHaveBeenCalledWith(
    "/conversations/chat/permissions/edit/revoke",
    {},
  );
});
