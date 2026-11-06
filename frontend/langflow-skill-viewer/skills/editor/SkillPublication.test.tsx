import { act, renderHook, waitFor } from "@testing-library/react";
import { api } from "@/controllers/API/api";
import { useRegistryComparison } from "./SkillPublication";
import type { Snapshot } from "../models";

jest.mock("@/controllers/API/api", () => ({ api: { get: jest.fn() } }));
jest.mock("@/customization/utils/urls", () => ({ getBaseUrl: () => "/api/v1/" }));
const get = api.get as jest.Mock;
const file = (path: string, text: string) => ({ path, text, kind: "text" as const, bytes: text.length, file_hash: path });
const base: Snapshot = { schema_version: "laomedo.skill-inspection.v1", skill_id: "unit", revision_id: "current", tree_hash: "current", files: [file("SKILL.md", "published"), file("refs/a.md", "original")] };
beforeEach(() => { get.mockReset(); get.mockResolvedValue({ data: base }); });

test("cumulative disclosure includes saved unpublished files as well as working edits", async () => {
  const files = [file("SKILL.md", "earlier saved edit"), file("refs/a.md", "new working edit")];
  const { result } = renderHook(() => useRegistryComparison("unit", "current", files));
  await waitFor(() => expect(result.current.base).toEqual(base));
  expect(result.current.paths).toEqual(["SKILL.md", "refs/a.md"]);
  // file_hash remains the saved hash while editing; compare actual working text.
  expect(files[1].file_hash).toBe(base.files[1].file_hash);
});

test("invalid identity fails closed; Retry recovers exact base without a write", async () => {
  get.mockResolvedValueOnce({ data: { ...base, tree_hash: "wrong" } });
  const { result } = renderHook(() => useRegistryComparison("unit", "current", base.files));
  await waitFor(() => expect(result.current.failed).toBe(true));
  expect(result.current.base).toBeNull();
  expect(result.current.showError).toBe(true);
  act(() => result.current.dismissError());
  expect(result.current.showError).toBe(false);
  act(() => result.current.retry());
  await waitFor(() => expect(result.current.base).toEqual(base));
  expect(result.current.paths).toEqual([]);
});
