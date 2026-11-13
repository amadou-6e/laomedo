import { fireEvent, render, screen } from "@testing-library/react";
import ConnectionForms from "./ConnectionForms";
import ConnectionInventory from "./ConnectionInventory";

jest.mock("@/components/ui/button", () => ({
  Button: ({ children, variant, ...props }: any) => (
    <button {...props}>{children}</button>
  ),
}));
jest.mock("@/components/ui/input", () => ({
  Input: (props: any) => <input {...props} />,
}));

describe("private connection entry", () => {
  it("clears the credential DOM before handing input to the request owner", () => {
    const submit = jest.fn((value) => {
      expect(screen.getByLabelText("Personal access token")).toHaveValue("");
      expect(value).toEqual({ token: "synthetic-credential" });
    });
    render(<ConnectionForms busy={false} submit={submit} close={jest.fn()} />);
    fireEvent.change(screen.getByLabelText("Personal access token"), {
      target: { value: "synthetic-credential" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Verify token" }));
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it("clears credential input before cancelling without submission", () => {
    const submit = jest.fn();
    const close = jest.fn(() =>
      expect(screen.getByLabelText("Personal access token")).toHaveValue(""),
    );
    render(<ConnectionForms busy={false} submit={submit} close={close} />);
    fireEvent.change(screen.getByLabelText("Personal access token"), {
      target: { value: "synthetic-credential" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(close).toHaveBeenCalledTimes(1);
    expect(submit).not.toHaveBeenCalled();
  });

  it("requires explicit repository selection instead of granting inventory access", () => {
    const confirm = jest.fn();
    render(
      <ConnectionInventory
        busy={false}
        confirm={confirm}
        cancel={jest.fn()}
        attempt={{
          request_id: "pending",
          connection_id: "connection",
          expires_at: 1,
          phase: "consent",
          authorization_url: null,
          inventory: {
            principal: { id: 1, login: "QA" },
            repositories: [{ id: 2, full_name: "qa/private", private: true }],
          },
        }}
      />,
    );
    const button = screen.getByRole("button", {
      name: "Save access",
    });
    expect(button).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox"));
    fireEvent.click(button);
    expect(confirm).toHaveBeenCalledWith([2]);
  });
});
