import { fireEvent, render, screen } from "@testing-library/react";
import NativeCommandMenu from "./NativeCommandMenu";
import { assistantRequest } from "./api";
jest.mock("./api", () => ({ assistantRequest: jest.fn() }));

test("offers matching commands from the selected session and selects without dispatch", async () => {
  jest.mocked(assistantRequest).mockResolvedValue({ state: "available", commands: [
    {name: "status", description: "Session status", executable: true},
    {name: "skills", description: "Skills", executable: true},
    {name: "secret", description: "Unavailable", executable: false},
  ] });
  const select = jest.fn();
  render(<NativeCommandMenu conversation="chat" text="/sta" onSelect={select} onClose={() => {}} />);
  fireEvent.click(await screen.findByRole("button", {name: /status/}));
  expect(select).toHaveBeenCalledWith("/status ");
  expect(screen.queryByRole("button", {name: /skills/})).toBeNull();
  expect(assistantRequest).toHaveBeenCalledTimes(1);
  expect(assistantRequest).toHaveBeenCalledWith("/conversations/chat/native-commands", undefined, expect.any(AbortSignal));
});

test("shows unavailable observed commands without granting execution", async () => {
  jest.mocked(assistantRequest).mockResolvedValue({state: "available", commands: [
    {name: "other", description: "Unsupported native command", executable: false, reason: "outside_assistant_command_policy"},
  ]});
  const select = jest.fn();
  render(<NativeCommandMenu conversation="chat" text="/" onSelect={select} onClose={() => {}} />);
  const command = await screen.findByRole("button", {name: /other/});
  expect(command).toBeDisabled();
  expect(command).toHaveAttribute("title", "This command needs a chat handler before it can run here.");
  expect(command).toHaveAccessibleDescription("This command needs a chat handler before it can run here.");
  fireEvent.click(command);
  expect(select).not.toHaveBeenCalled();
});

test.each(["claude", "opencode"])("previews %s native entry points without starting inference", provider => {
  jest.clearAllMocks();
  render(<NativeCommandMenu conversation="" provider={provider} text="/" onSelect={() => {}} onClose={() => {}} />);
  expect(screen.getByText(/Start a chat to discover/)).toBeVisible();
  expect(screen.getByRole("button", {name: provider === "claude" ? /compact/ : /init/})).toBeDisabled();
  expect(screen.getByRole("button", {name: provider === "claude" ? /login/ : /connect/})).not.toBeDisabled();
  expect(assistantRequest).not.toHaveBeenCalled();
});

test("previews supported Codex commands before a session without granting execution or creating a session", () => {
  jest.clearAllMocks();
  render(<NativeCommandMenu conversation="" text="/" onSelect={() => {}} onClose={() => {}} />);
  expect(screen.getByText(/Send \/status to start a session without using the model/)).toBeVisible();
  expect(screen.getByRole("button", {name: /status.*Start a session/})).not.toBeDisabled();
  expect(screen.getByRole("button", {name: /mcp.*Show configured/})).toBeDisabled();
  expect(screen.getByRole("button", {name: /compact.*Compact/})).toBeDisabled();
  expect(screen.getByRole("button", {name: /review-branch/})).toBeDisabled();
  expect(screen.getByRole("button", {name: /logout/})).not.toBeDisabled();
  expect(assistantRequest).not.toHaveBeenCalled();
});
