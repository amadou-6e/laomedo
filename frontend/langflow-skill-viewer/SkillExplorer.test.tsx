import { fireEvent, render, screen, within } from "@testing-library/react";
import { useState } from "react";
import SkillExplorer from "./SkillExplorer";
import { SkillFileIcon } from "./SkillIcons";
import type { SkillFile } from "./SkillHistory";

const file = (path: string): SkillFile => ({ path, kind: "text", text: "", bytes: 0, file_hash: "unit-only" });

function ExplorerExample() {
  const [collapsed, setCollapsed] = useState(new Set<string>());
  const [active, setActive] = useState("SKILL.md");
  return <SkillExplorer files={[file("SKILL.md"), file("references/rules.md")]}
    active={active} select={setActive} collapsed={collapsed}
    onToggle={(path) => setCollapsed((current) => current.has(path) ? new Set() : new Set([path]))} />;
}

test("file logos are decorative and folder chevrons follow disclosure without changing file selection", () => {
  render(<ExplorerExample />);
  const root = screen.getByRole("button", { name: "SKILL.md", exact: true });
  const folder = screen.getByRole("button", { name: "references", exact: true });
  const child = screen.getByRole("button", { name: "rules.md", exact: true });
  expect(root.querySelector('[data-file-type="markdown"]')).toHaveAttribute("aria-hidden", "true");
  expect(root).not.toHaveAttribute("aria-expanded");
  expect(child).toHaveAttribute("title", "references/rules.md");
  fireEvent.click(child);
  expect(child).toHaveAttribute("aria-current", "true");
  expect(folder.querySelector('[data-chevron="down"]')).toHaveAttribute("aria-hidden", "true");
  fireEvent.click(folder);
  expect(folder).toHaveAttribute("aria-expanded", "false");
  expect(folder.querySelector('[data-chevron="right"]')).toBeInTheDocument();
  expect(child).not.toBeVisible();
  fireEvent.click(folder);
  expect(child).toBeVisible();
  expect(child).toHaveAttribute("aria-current", "true");
  expect(within(root).queryByRole("img")).not.toBeInTheDocument();
});

test.each([
  ["SKILL.MD", "markdown"], ["nested/worker.py", "python"], ["module.mjs", "javascript"],
  ["view.tsx", "typescript"], ["config.jsonc", "json"], ["config.yml", "yaml"],
  ["pyproject.toml", "toml"], ["run.sh", "shell"], ["page.html", "html"],
  ["style.css", "css"], ["main.rs", "rust"], ["main.go", "go"],
  ["Dockerfile", "docker"], ["Dockerfile.runner", "docker"], ["diagram.svg", "image"],
  ["image.PNG", "image"], ["data.bin", "binary"], ["unknown.ext", "file"],
  ["README", "file"], ["py", "file"], ["", "file"],
])("%s has a bundled %s icon with no external asset", (path, expected) => {
  const { container } = render(<SkillFileIcon path={path} />);
  expect(container.querySelector("[data-file-type]")).toHaveAttribute("data-file-type", expected);
  expect(container.querySelector("svg")).toHaveAttribute("height", "16");
  expect(container.querySelector("svg")).toHaveAttribute("focusable", "false");
  expect(container.querySelector("img, image, use, script")).toBeNull();
});
