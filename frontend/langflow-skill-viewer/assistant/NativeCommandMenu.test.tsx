import { fireEvent, render, screen } from "@testing-library/react";
import NativeCommandMenu from "./NativeCommandMenu";
import { assistantRequest } from "./api";
jest.mock("./api", () => ({ assistantRequest: jest.fn() }));

test("offers only matching executable commands from the selected session and selects without dispatch", async () => {
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

test("does not invent a catalog or create a session for a new conversation", () => {
  jest.clearAllMocks();
  render(<NativeCommandMenu conversation="" text="/" onSelect={() => {}} onClose={() => {}} />);
  expect(screen.getByText(/after the first response/)).toBeVisible();
  expect(assistantRequest).not.toHaveBeenCalled();
});
