import { act, renderHook, waitFor } from "@testing-library/react";
import { api } from "@/controllers/API/api";
import { useSkillEditing } from "./SkillEditing";
import type { Snapshot } from "./SkillHistory";

jest.mock("@/controllers/API/api", () => ({ api: { post: jest.fn() } }));
jest.mock("@/customization/utils/urls", () => ({ getBaseUrl: () => "/api/v1/" }));
const post = api.post as jest.Mock;
const snapshot: Snapshot = { schema_version: "laomedo.skill-inspection.v1", skill_id: "unit", revision_id: "old", tree_hash: "old",
  files: ["SKILL.md", "refs/a.md"].map((path) => ({ path, text: "before", kind: "text", bytes: 6, file_hash: path })) };
const state = { skill_id: "unit", selected_revision: "old", head_revision: "old", head_commit: "commit", latest_revision: "canonical", can_edit: true, can_publish: true, edit_enabled: true };
beforeEach(() => { post.mockReset(); post.mockResolvedValue({ data: state }); });

test("following a new revision clears old tree redo rather than restoring stale bytes", async () => {
  const saved = jest.fn();
  post.mockImplementation((_url, body) => Promise.resolve({ data: { ...state, selected_revision: body.revision_id, head_revision: body.revision_id } }));
  const { result, rerender } = renderHook(({ revision, value }) => useSkillEditing('unit', revision, value, saved), { initialProps: { revision: 'old', value: snapshot } });
  await waitFor(() => expect(result.current.editing).toBe(true));
  act(() => { result.current.replaceFiles(snapshot.files.map((file) => file.path === 'refs/a.md' ? { ...file, path: 'a.md' } : file), ['refs']); });
  act(() => { result.current.undoFiles(); });
  expect(result.current.dirty).toBe(false);
  const newer: Snapshot = { ...snapshot, revision_id: 'new-head', tree_hash: 'new-head', files: snapshot.files.map((file) => ({ ...file, text: 'newer saved bytes' })) };
  rerender({ revision: 'new-head', value: newer });
  await waitFor(() => expect(result.current.state?.selected_revision).toBe('new-head'));
  act(() => { expect(result.current.undoFiles(false)).toBe(false); });
  expect(result.current.files.map((file) => file.text)).toEqual(['newer saved bytes', 'newer saved bytes']);
  expect(result.current.files.map((file) => file.path)).toEqual(['SKILL.md', 'refs/a.md']);
  expect(result.current.dirty).toBe(false);
});

test("editing is immediately enabled; one Publish saves the whole batch then promotes its exact commit", async () => {
  const saved = jest.fn();
  const { result } = renderHook(() => useSkillEditing("unit", "old", snapshot, saved));
  await waitFor(() => expect(result.current.state).toEqual(state));
  expect(result.current.editing).toBe(true);
  expect(result.current.dirty).toBe(false);
  act(() => { result.current.update("SKILL.md", "after"); result.current.update("refs/a.md", "also after"); result.current.setMessage("Explain both edits"); });
  expect(result.current.changes).toHaveLength(2);
  post.mockImplementation((url) => Promise.resolve({ data: url.endsWith("/save") ? { skill: { skill_id: "unit", revision_id: "new", tree_hash: "new" }, commit: { commit_id: "next" } } : url.endsWith("/publish") ? { skill_id: "unit", revision_id: "new", commit_id: "next", promotion_performed: true } : state }));
  act(() => result.current.publish());
  await waitFor(() => expect(saved).toHaveBeenCalledWith("new"));
  const calls = post.mock.calls.filter(([url]) => url.endsWith("/save"));
  expect(calls).toHaveLength(1);
  expect(calls[0][1]).toMatchObject({ skill_id: "unit", revision_id: "old", commit_id: "commit", operation: { action: "modify", message: "Explain both edits", files: [{ path: "SKILL.md", content: "after" }, { path: "refs/a.md", content: "also after" }] } });
  await waitFor(() => expect(result.current.status).toMatch(/^Published/));
  const publication = post.mock.calls.filter(([url]) => url.endsWith("/publish"));
  expect(publication).toHaveLength(1);
  expect(publication[0][1]).toEqual({ skill_id: "unit", revision_id: "new", commit_id: "next", expected_latest: "canonical" });
  expect(result.current.dirty).toBe(false);
});

test("uncertain save locks editing and reconciles exactly the same UUID and bytes", async () => {
  const saved = jest.fn();
  const { result } = renderHook(() => useSkillEditing("unit", "old", snapshot, saved));
  await waitFor(() => expect(result.current.state).toEqual(state));
  act(() => { result.current.update("SKILL.md", "after"); result.current.setMessage("Manual edit"); });
  post.mockRejectedValueOnce(Error("connection lost"));
  act(() => result.current.publish());
  await waitFor(() => expect(result.current.error).toBe("skill_manual_unavailable"));
  const pending = result.current.pending;
  expect(pending?.action).toBe("save");
  expect(result.current.changes).toHaveLength(1);
  act(() => result.current.discard());
  expect(result.current.changes).toHaveLength(1);
  post.mockResolvedValueOnce({ data: { skill: { skill_id: "unit", revision_id: "new", tree_hash: "new" }, commit: { commit_id: "next" } } });
  post.mockResolvedValueOnce({ data: { skill_id: "unit", revision_id: "new", commit_id: "next", promotion_performed: true } });
  act(() => result.current.reconcile());
  await waitFor(() => expect(saved).toHaveBeenCalledWith("new"));
  const saves = post.mock.calls.filter(([url]) => url.endsWith("/save"));
  expect(saves[0][1]).toEqual(saves[1][1]);
});

test("policy refusal preserves the buffer and disables no unrelated viewing controls", async () => {
  const { result } = renderHook(() => useSkillEditing("unit", "old", snapshot, jest.fn()));
  await waitFor(() => expect(result.current.state).toEqual(state));
  act(() => { result.current.update("SKILL.md", "after"); result.current.setMessage("Manual edit"); });
  post.mockRejectedValueOnce({ response: { data: { detail: { code: "skill_manual_policy_denied" } } } });
  act(() => result.current.publish());
  await waitFor(() => expect(result.current.error).toBe("skill_manual_policy_denied"));
  expect(result.current.pending).toBeNull();
  expect(result.current.files[0].text).toBe("after");
  expect(result.current.editing).toBe(true);
});

test("an uncertain publication reconciles its exact candidate and base without a second save", async () => {
  const { result } = renderHook(() => useSkillEditing("unit", "old", snapshot, jest.fn()));
  await waitFor(() => expect(result.current.state).toEqual(state));
  act(() => result.current.update("SKILL.md", "after"));
  post.mockResolvedValueOnce({ data: { skill: { skill_id: "unit", revision_id: "new", tree_hash: "new" }, commit: { commit_id: "next" } } });
  post.mockRejectedValueOnce(Error("response lost"));
  act(() => result.current.publish());
  await waitFor(() => expect(result.current.error).toBe("skill_manual_unavailable"));
  expect(result.current.pending?.action).toBe("publish");
  expect(result.current.dirty).toBe(true);
  expect(result.current.candidate).toEqual({ revision: "new", commit: "next" });
  post.mockResolvedValueOnce({ data: { skill_id: "unit", revision_id: "new", commit_id: "next", promotion_performed: true } });
  act(() => result.current.reconcile());
  await waitFor(() => expect(result.current.status).toMatch(/^Published/));
  expect(post.mock.calls.filter(([url]) => url.endsWith("/save"))).toHaveLength(1);
  const publications = post.mock.calls.filter(([url]) => url.endsWith("/publish"));
  expect(publications[0][1]).toEqual(publications[1][1]);
});

test("clean workspace follows editing head; dirty workspace never silently rebases", async () => {
  const saved = jest.fn();
  const { result } = renderHook(() => useSkillEditing("unit", "old", snapshot, saved));
  await waitFor(() => expect(result.current.state).toEqual(state));
  act(() => result.current.update("SKILL.md", "after"));
  post.mockResolvedValueOnce({ data: { ...state, head_revision: "newer", can_edit: false } });
  act(() => result.current.refresh());
  await waitFor(() => expect(result.current.state?.head_revision).toBe("newer"));
  expect(saved).not.toHaveBeenCalled();
  expect(result.current.files[0].text).toBe("after");
  act(() => result.current.discard());
  expect(saved).toHaveBeenCalledWith("newer");
});

test("returning a file to its original text hides publication controls and Discard never writes", async () => {
  const { result } = renderHook(() => useSkillEditing("unit", "old", snapshot, jest.fn()));
  await waitFor(() => expect(result.current.state).toEqual(state));
  act(() => result.current.update("SKILL.md", "after"));
  expect(result.current.dirty).toBe(true);
  act(() => result.current.update("SKILL.md", "before"));
  expect(result.current.dirty).toBe(false);
  act(() => result.current.discard());
  expect(post.mock.calls.every(([url]) => url.endsWith("/editor"))).toBe(true);
});

test("dismissing a controls lookup failure leaves recovery available", async () => {
  post.mockRejectedValueOnce(Error("offline"));
  const { result } = renderHook(() => useSkillEditing("unit", "old", snapshot, jest.fn()));
  await waitFor(() => expect(result.current.controlsUnavailable).toBe(true));
  act(() => result.current.dismissError());
  expect(result.current.error).toBe("");
  expect(result.current.controlsUnavailable).toBe(true);
  act(() => result.current.refresh());
  await waitFor(() => expect(result.current.state).toEqual(state));
  expect(result.current.controlsUnavailable).toBe(false);
});
