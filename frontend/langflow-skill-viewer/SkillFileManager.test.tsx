import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useEffect, useRef, useState } from "react";
import { api } from "@/controllers/API/api";
import SkillFileManager, { type SkillFileManagerHandle } from "./SkillFileManager";
import { useSkillEditing } from "./SkillEditing";
import type { Snapshot } from "./SkillHistory";
import { TextDecoder, TextEncoder } from "util";
Object.assign(global, { TextDecoder, TextEncoder });

jest.mock("@/controllers/API/api", () => ({ api: { post: jest.fn() } }));
jest.mock("@/customization/utils/urls", () => ({ getBaseUrl: () => "/api/v1/" }));
const post = api.post as jest.Mock;
const snapshot: Snapshot = { schema_version: "laomedo.skill-inspection.v1", skill_id: "unit", revision_id: "base", tree_hash: "base",
  files: ["SKILL.md", "refs/a.md"].map((path) => ({ path, kind: "text", text: "original", bytes: 8, file_hash: path })) };
const state = { skill_id: "unit", selected_revision: "base", head_revision: "base", head_commit: "commit", latest_revision: "base", can_edit: true, can_publish: true, edit_enabled: true };
function Example({ reason = "" }: { reason?: string }) {
  const [portal, setPortal] = useState<HTMLDivElement | null>(null), actions = useRef<SkillFileManagerHandle>(null);
  const manual = useSkillEditing("unit", "base", snapshot, () => {});
  useEffect(() => {
    // The real BaseModal guards Escape at document capture, before Radix's menu
    // consumes bubbling keyboard events. Exercise that integration contract.
    const dismiss = (event: KeyboardEvent) => { if (event.key === "Escape" && actions.current?.dismiss()) { event.preventDefault(); event.stopImmediatePropagation(); } };
    document.addEventListener("keydown", dismiss, true);
    return () => document.removeEventListener("keydown", dismiss, true);
  }, []);
  return <div ref={setPortal} role="dialog" onKeyDown={(event) => { if (event.key === "Escape" && actions.current?.dismiss()) { event.preventDefault(); event.stopPropagation(); } }}>
    <span>{manual.editing ? "Ready" : "Loading controls"}</span>
    <output data-testid="edit-grant">{String(manual.state?.can_edit)}</output>
    <button type="button" onClick={manual.refresh}>Refresh controls</button>
    <SkillFileManager ref={actions} manual={manual} files={manual.files} active="SKILL.md" collapsed={new Set()} select={() => {}} onToggle={() => {}}
      portal={portal} disabledReason={reason || (!manual.editing ? "Read only" : "")} onImporting={() => {}} onRemap={() => {}} />
    {manual.error && <p role="alert">{manual.error}</p>}
  </div>;
}
beforeEach(() => { post.mockReset(); post.mockResolvedValue({ data: state }); });

test("keyboard context menu stays inside the dialog, core entrypoint is protected and Escape keeps the workspace", async () => {
  render(<Example />); await screen.findByText("Ready");
  const file = screen.getByRole("button", { name: "SKILL.md", exact: true });
  fireEvent.keyDown(file, { key: "F10", shiftKey: true });
  const menu = await screen.findByRole("menu", { name: "File actions: SKILL.md" });
  expect(menu.closest('[role="dialog"]')).toBe(screen.getByRole("dialog"));
  expect(within(menu).getByRole("menuitem", { name: "Rename..." })).toHaveAttribute("data-disabled");
  expect(within(menu).getByRole("menuitem", { name: "Delete..." })).toHaveAttribute("data-disabled");
  expect(within(menu).getByRole("menuitem", { name: "Copy relative path" })).not.toHaveAttribute("data-disabled");
  fireEvent.contextMenu(within(menu).getByRole("menuitem", { name: "Copy relative path" }), { clientX: 10, clientY: 10 });
  expect(screen.getByRole("menu")).toHaveAttribute("aria-label", "File actions: SKILL.md");
  fireEvent.keyDown(menu, { key: "Escape" });
  await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

test("rename stages a new path without writing and deletion cancellation preserves it", async () => {
  render(<Example />); await screen.findByText("Ready");
  fireEvent.contextMenu(screen.getByRole("button", { name: "a.md", exact: true }), { clientX: 10, clientY: 10 });
  fireEvent.click(await screen.findByRole("menuitem", { name: "Rename..." }));
  const form = await screen.findByRole("form", { name: "Rename refs/a.md" });
  fireEvent.change(within(form).getByRole("textbox", { name: "Name" }), { target: { value: "renamed.md" } });
  fireEvent.click(within(form).getByRole("button", { name: "Rename", exact: true }));
  const renamed = await screen.findByRole("button", { name: "renamed.md", exact: true });
  expect(screen.queryByRole("button", { name: "a.md", exact: true })).toBeNull();
  fireEvent.contextMenu(renamed, { clientX: 10, clientY: 10 });fireEvent.click(await screen.findByRole("menuitem", { name: "Delete..." }));
  const deletion = await screen.findByRole("form", { name: "Delete refs/renamed.md" });
  fireEvent.click(within(deletion).getByRole("button", { name: "Cancel", exact: true }));
  expect(renamed).toBeInTheDocument();
  expect(post.mock.calls.every(([url]) => url.endsWith("/editor"))).toBe(true);
});

test("readonly mutations show the reason; denied clipboard exposes only the relative path for manual copying", async () => {
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: jest.fn().mockRejectedValue(Error("private failure")) } });
  render(<Example reason="Historical comparison is read only." />); await screen.findByText("Ready");
  fireEvent.contextMenu(screen.getByRole("button", { name: "a.md", exact: true }), { clientX: 10, clientY: 10 });
  const menu = await screen.findByRole("menu");
  expect(within(menu).getByText("Historical comparison is read only.")).toBeInTheDocument();
  expect(within(menu).getByRole("menuitem", { name: "Upload files..." })).toHaveAttribute("data-disabled");
  fireEvent.click(within(menu).getByRole("menuitem", { name: "Copy relative path" }));
  const field = await screen.findByRole("textbox", { name: "Relative path" });expect(field).toHaveValue("refs/a.md");expect(field).toHaveAttribute("readonly");
  expect(await screen.findByRole("alert")).toHaveTextContent("skill_manual_clipboard_unavailable");
  expect(screen.queryByText("private failure")).toBeNull();
});

test("a grant revoked while a local file is being read cannot stage that file through an old closure", async () => {
  let resolve!: (bytes: ArrayBuffer) => void;
  const value = new File(["A"], "new.md");
  Object.defineProperty(value, "arrayBuffer", { value: () => new Promise<ArrayBuffer>((done) => { resolve = done; }) });
  render(<Example />); await screen.findByText("Ready");
  fireEvent.change(screen.getByLabelText("Upload Skill files"), { target: { files: [value] } });
  await waitFor(() => expect(resolve).toBeDefined());
  post.mockResolvedValueOnce({ data: { ...state, can_edit: false, edit_enabled: false } });
  fireEvent.click(screen.getByRole("button", { name: "Refresh controls" }));
  await waitFor(() => expect(screen.getByTestId("edit-grant")).toHaveTextContent("false"));
  resolve(new Uint8Array([65]).buffer);
  expect(await screen.findByRole("alert")).toHaveTextContent("skill_manual_not_authorized");
  expect(screen.queryByRole("button", { name: "new.md", exact: true })).toBeNull();
  expect(post.mock.calls.every(([url]) => url.endsWith("/editor"))).toBe(true);
});
