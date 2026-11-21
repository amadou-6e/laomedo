import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import AccountSelection from "./AccountSelection";

jest.mock("./ProviderIcon", () => ({ __esModule: true, default: () => null }));

const accounts = [
  { connection_id: "personal", generation: 1, provider: "codex", label: "Personal", lifecycle: "connected", auth_state: "ready" },
  { connection_id: "work", generation: 2, provider: "codex", label: "Work", lifecycle: "connected", auth_state: "ready" },
];

test("allows the owner to cancel settings navigation when draft retention fails", () => {
  const retain = jest.fn(() => false);
  render(<AccountSelection accounts={accounts} provider="codex" selected="personal" generation={1} disabled={false} onSelect={jest.fn()} onManageAccounts={retain} />);
  fireEvent.click(screen.getByRole("button", {name: "Account"}));
  const event = new MouseEvent("click", {bubbles: true, cancelable: true});
  screen.getByRole("menuitem", {name: "Manage accounts"}).dispatchEvent(event);
  expect(retain).toHaveBeenCalledTimes(1);
  expect(event.defaultPrevented).toBe(true);
});

test("selects an exact saved account with keyboard navigation and restores trigger focus", async () => {
  const select = jest.fn();
  render(<AccountSelection accounts={accounts} provider="codex" selected="personal" generation={1} disabled={false} onSelect={select} />);
  const trigger = screen.getByRole("button", { name: "Account" });
  expect(trigger).toHaveAccessibleDescription("Personal");
  fireEvent.click(trigger);
  const personal = await screen.findByRole("menuitemradio", { name: "Personal" });
  expect(personal).toHaveAttribute("aria-checked", "true");
  personal.focus();
  fireEvent.keyDown(personal, { key: "ArrowDown" });
  expect(screen.getByRole("menuitemradio", { name: "Work" })).toHaveFocus();
  fireEvent.click(screen.getByRole("menuitemradio", { name: "Work" }));
  expect(select).toHaveBeenCalledTimes(1);
  expect(select).toHaveBeenCalledWith(accounts[1]);
  await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
  await waitFor(() => expect(trigger).toHaveFocus());
});

test("names an unavailable provider and links account settings without selecting another provider", async () => {
  const select = jest.fn();
  render(<AccountSelection accounts={[]} provider="claude" disabled={false} onSelect={select} />);
  fireEvent.click(screen.getByRole("button", { name: "Account" }));
  expect(await screen.findByText("No connected Claude account.")).toBeVisible();
  expect(screen.getByRole("menuitem", { name: "Manage accounts" })).toHaveAttribute("href", "/settings/providers");
  expect(screen.getByRole("menuitem", { name: "Manage accounts" })).not.toHaveAttribute("target");
  expect(select).not.toHaveBeenCalled();
});
