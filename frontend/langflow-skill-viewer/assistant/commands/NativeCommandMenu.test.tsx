import { fireEvent, render, screen } from "@testing-library/react";
import NativeCommandMenu from "./NativeCommandMenu";
import { assistantRequest } from "../api";
jest.mock("../api", () => ({ assistantRequest: jest.fn() }));
beforeEach(() => jest.mocked(assistantRequest).mockReset());

test("selects a discovered Codex system skill using its native dollar syntax", async () => {
  jest.mocked(assistantRequest).mockResolvedValue({state: "available", commands: [
    {name: "$skill-creator", kind: "skill", description: "Create a skill", executable: true, accepts_arguments: true},
  ]});
  const select = jest.fn();
  render(<NativeCommandMenu conversation="chat" text="/skill-c" onSelect={select} onClose={() => {}} />);
  fireEvent.click(await screen.findByRole("button", {name: /\$skill-creator/}));
  expect(select).toHaveBeenCalledWith("$skill-creator ");
  expect(screen.queryByText("Skills")).toBeNull();
  expect(screen.queryByText("Commands")).toBeNull();
});

test("groups native skills separately and explains unsupported provider configuration", async () => {
  jest.mocked(assistantRequest).mockResolvedValue({state: "available", commands: [
    {name: "customize-opencode", kind: "skill", description: "Configure OpenCode", executable: false, reason: "native_skill_requires_provider_configuration"},
    {name: "init", kind: "command", description: "Initialize", executable: true},
  ]});
  render(<NativeCommandMenu conversation="chat" provider="opencode" text="/" onSelect={jest.fn()} onClose={() => {}} />);
  expect(await screen.findByText("Skills")).toBeVisible();
  const skill = screen.getByRole("button", {name: /customize-opencode/});
  expect(skill).toBeDisabled();
  expect(skill).toHaveAccessibleDescription("This skill edits provider configuration, which is managed by Laomedo.");
  expect(screen.getByText("Commands")).toBeVisible();
  expect(screen.getByText("App-managed settings")).toBeVisible();
  expect(screen.getByText("Commands").compareDocumentPosition(screen.getByText("Skills")) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test("filters both groups and removes grouping when only one group matches", async () => {
  jest.mocked(assistantRequest).mockResolvedValue({state: "available", commands: [
    {name: "context-skill", kind: "skill", description: "Skill context", executable: true},
    {name: "context-extra", kind: "command", description: "Unsupported context", executable: false, reason: "outside_assistant_command_policy"},
    {name: "context", kind: "command", description: "Session context", executable: true},
  ]});
  const props = {conversation: "chat", provider: "claude", onSelect: jest.fn(), onClose: jest.fn()};
  const view = render(<NativeCommandMenu {...props} text="/context" />);
  await screen.findByText("Skills");
  const buttons = screen.getAllByRole("button");
  expect(buttons.map(button => button.textContent)).toEqual([
    expect.stringContaining("/contextSession context"),
    expect.stringContaining("/context-extraUnsupported contextNot integrated"),
    expect.stringContaining("/context-skillSkill context"),
  ]);
  view.rerender(<NativeCommandMenu {...props} text="/context-s" />);
  expect(screen.queryByText("Commands")).toBeNull();
  expect(screen.queryByText("Skills")).toBeNull();
  expect(screen.getAllByRole("button")).toHaveLength(1);
  view.rerender(<NativeCommandMenu {...props} text="/context-e" />);
  expect(screen.queryByText("Commands")).toBeNull();
  expect(screen.queryByText("Skills")).toBeNull();
  expect(screen.getByText("Not integrated")).toBeVisible();
  view.rerender(<NativeCommandMenu {...props} text="/no-match" />);
  expect(screen.queryByRole("button")).toBeNull();
  expect(screen.queryByText("Skills")).toBeNull();
  expect(screen.getByText(/No matching command/)).toBeVisible();
});

test("refreshes Claude commands after the native thread settles while the menu stays open", async () => {
  jest.mocked(assistantRequest).mockResolvedValueOnce({state: "unavailable", reason: "native_session_not_observed", commands: []});
  const props = {conversation: "chat", provider: "claude", runId: "run", text: "/usa", onSelect: jest.fn(), onClose: jest.fn()};
  const view = render(<NativeCommandMenu {...props} active />);
  await screen.findByText("Native commands are unavailable in this session.");
  jest.mocked(assistantRequest).mockResolvedValueOnce({state: "available", commands: [{name: "usage", description: "Show native usage", executable: true}]});
  view.rerender(<NativeCommandMenu {...props} active={false} threadId="thread" />);
  expect(await screen.findByRole("button", {name: /usage/})).not.toBeDisabled();
  expect(props.onSelect).not.toHaveBeenCalled();
});

test("offers retry after failed discovery even when application commands are present", async () => {
  jest.mocked(assistantRequest).mockRejectedValueOnce(new Error("unavailable"));
  render(<NativeCommandMenu conversation="chat" provider="claude" text="/" onSelect={jest.fn()} onClose={() => {}} />);
  const retry = await screen.findByRole("button", {name: "Could not load native commands. Retry"});
  expect(screen.getByRole("button", {name: /\/login/})).toBeVisible();
  jest.mocked(assistantRequest).mockResolvedValueOnce({state: "available", commands: [{name: "usage", description: "Show usage", executable: true}]});
  fireEvent.click(retry);
  expect(await screen.findByRole("button", {name: /usage/})).not.toBeDisabled();
});

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
