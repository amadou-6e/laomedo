import { fireEvent, render, screen } from "@testing-library/react";
import ConnectionInventory from "./ConnectionInventory";
import type { PendingConnection } from "./types";

jest.mock("@/components/ui/button", () => ({
  Button: ({ children, variant, ...props }: any) => (
    <button {...props}>{children}</button>
  ),
}));
jest.mock("@/components/ui/input", () => ({
  Input: (props: any) => <input {...props} />,
}));

test("editing preserves only saved repositories still present in the verified inventory", () => {
  const attempt: PendingConnection = {
    request_id: "edit",
    connection_id: "saved",
    expires_at: 9999999999,
    phase: "consent",
    authorization_url: null,
    inventory: {
      principal: { id: 1, login: "owner" },
      repositories: [{ id: 7, full_name: "owner/allowed", private: true }],
    },
  };
  const confirm = jest.fn();
  render(
    <ConnectionInventory
      attempt={attempt}
      busy={false}
      confirm={confirm}
      cancel={jest.fn()}
      initialRepositoryIds={[7, 99]}
    />,
  );
  expect(screen.getByRole("checkbox")).toBeChecked();
  fireEvent.click(screen.getByRole("button", { name: "Save access" }));
  expect(confirm).toHaveBeenCalledWith([7]);
});

test.each([1, 5, 6])(
  "repository search is available only above five choices (%i)",
  (count) => {
    const repositories = Array.from({ length: count }, (_, id) => ({
      id,
      full_name: `owner/repo-${id}`,
      private: true,
    }));
    const attempt: PendingConnection = {
      request_id: "pending",
      connection_id: "connection",
      expires_at: 9999999999,
      phase: "consent",
      authorization_url: null,
      inventory: { principal: { id: 1, login: "owner" }, repositories },
    };
    const confirm = jest.fn();
    render(
      <ConnectionInventory
        attempt={attempt}
        busy={false}
        confirm={confirm}
        cancel={jest.fn()}
      />,
    );
    expect(
      Boolean(screen.queryByRole("textbox", { name: "Search repositories" })),
    ).toBe(count > 5);
    if (count > 5) {
      fireEvent.change(screen.getByRole("textbox"), {
        target: { value: "repo-5" },
      });
      expect(screen.getAllByRole("checkbox")).toHaveLength(1);
      fireEvent.click(screen.getByRole("checkbox"));
      fireEvent.click(screen.getByRole("button", { name: "Save access" }));
      expect(confirm).toHaveBeenCalledWith([5]);
    }
  },
);
