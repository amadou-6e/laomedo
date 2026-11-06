import { fireEvent, render, screen } from "@testing-library/react";
import SkillSearch, { searchSkill } from "./SkillSearch";
import type { SkillFile } from "../models";

const file = (path: string, text: string | null): SkillFile => ({ path, text, kind: text == null ? "binary" : "text", bytes: text?.length || 0, file_hash: "test-only" });

test("literal matching covers nested files, line endings, case, Unicode and excludes binary", () => {
  const files = [file("SKILL.md", "Proposal\r\n[x].*\nİ proposal"), file("refs/a.md", "proposal\rPROPOSAL"), file("picture.png", null)];
  expect(searchSkill(files, "proposal", false).matches.map(({ path, line, column }) => [path, line, column])).toEqual([
    ["SKILL.md", 1, 1], ["SKILL.md", 3, 3], ["refs/a.md", 1, 1], ["refs/a.md", 2, 1],
  ]);
  expect(searchSkill(files, "proposal", true).matches).toHaveLength(2);
  expect(searchSkill(files, "[x].*", false).matches[0].line).toBe(2);
  expect(searchSkill(files, "", false).matches).toEqual([]);
  expect(searchSkill(files, "missing", false).matches).toEqual([]);
});

test("result rendering is bounded and explicitly discloses truncation", () => {
  const files = [file("large.md", Array(501).fill("match").join("\n"))];
  expect(searchSkill(files, "match", false)).toMatchObject({ truncated: true });
  expect(searchSkill(files, "match", false).matches).toHaveLength(500);
  expect(searchSkill([file("exact.md", Array(500).fill("match").join("\n"))], "match", false).truncated).toBe(false);
});

test("grouped results select a line repeatedly, support case and no-match recovery, and render markup inertly", () => {
  const onSelect = jest.fn();
  render(<SkillSearch files={[file("SKILL.md", "Proposal"), file("references/a.md", "<script>proposal</script>")]} onSelect={onSelect} />);
  const input = screen.getByRole("searchbox", { name: "Search all Skill files" });
  fireEvent.change(input, { target: { value: "proposal" } });
  expect(screen.getByRole("status")).toHaveTextContent("2 matching lines in 2 files");
  const result = screen.getByRole("button", { name: "references/a.md, line 1" });
  fireEvent.click(result); fireEvent.click(result);
  expect(onSelect).toHaveBeenCalledTimes(2);
  expect(onSelect).toHaveBeenLastCalledWith(expect.objectContaining({ path: "references/a.md", line: 1, column: 9 }));
  expect(document.querySelector("script")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Match case" }));
  expect(screen.getByRole("status")).toHaveTextContent("1 matching line in 1 file");
  fireEvent.change(input, { target: { value: "absent" } });
  expect(screen.getByRole("status")).toHaveTextContent("No matches");
  fireEvent.change(input, { target: { value: "" } });
  expect(screen.getByRole("status")).toHaveTextContent("Search working text files");
});

test("search folders and files disclose independently and preserve collapse through query changes", () => {
  render(<SkillSearch files={[file("refs/nested/a.md", "proposal"), file("refs/b.md", "proposal")]} onSelect={jest.fn()} />);
  const input = screen.getByRole("searchbox");
  fireEvent.change(input, { target: { value: "proposal" } });
  const folder = screen.getByRole("button", { name: "Search folder: refs" });
  const fileGroup = screen.getByRole("button", { name: "Search file: refs/nested/a.md" });
  expect(fileGroup).toHaveAttribute("aria-expanded", "true");
  fireEvent.click(fileGroup);
  expect(screen.getByRole("button", { name: "refs/nested/a.md, line 1", hidden: true })).not.toBeVisible();
  fireEvent.click(folder);
  expect(fileGroup).not.toBeVisible();
  fireEvent.change(input, { target: { value: "prop" } });
  expect(folder).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(folder);
  expect(fileGroup).toHaveAttribute("aria-expanded", "false");
  fireEvent.click(fileGroup);
  expect(screen.getByRole("button", { name: "refs/nested/a.md, line 1" })).toBeVisible();
});
