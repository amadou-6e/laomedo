import { fireEvent, render, screen } from "@testing-library/react";
import SkillOverview, { bundlePath, skillDescription } from "./SkillOverview";
import type { Snapshot } from "./SkillHistory";
jest.unmock("react-markdown");
const textFile = (path: string, text: string) => ({ path, text, kind: "text" as const, bytes: text.length, file_hash: path });
const snapshot: Snapshot = { schema_version: "laomedo.skill-inspection.v1", skill_id: "real-contract", revision_id: "pinned", tree_hash: "pinned", files: [
  textFile("SKILL.md", '---\nname: real-contract\ndescription: "Explain the purpose. A second sentence."\n---\n# Instructions\nUse the selected PR.'),
  textFile("OVERVIEW.md", '# How it works\nRead the PR, propose a change, and let the host validate it.\n\n![Flow](assets/flow.svg)\n![Remote](https://external.invalid/image.png)\n[Details](references/details.md)\n<script>bad()</script>'),
  textFile("assets/flow.svg", '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 30"><text x="1" y="20">Read then propose</text><script>bad()</script><foreignObject>bad</foreignObject><image href="https://external.invalid/track"/></svg>'),
  textFile("references/details.md", '# More detail\n![Diagram](../assets/flow.svg)'),
] };

test("summary is visible, collapsible, and full documentation opens separately", () => {
  render(<SkillOverview snapshot={snapshot} />);
  expect(screen.getByTestId("skill-summary")).toHaveTextContent("Explain the purpose.");
  expect(screen.queryByRole("article")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /About this skill/ }));
  expect(screen.queryByTestId("skill-summary")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Read full overview" }));
  expect(screen.getByRole("article", { name: "Full skill overview" })).toHaveTextContent("How it works");
  expect(screen.getByTestId("skill-summary")).toBeVisible();
  fireEvent.click(screen.getByRole("button", { name: "Close full overview" }));
  expect(screen.queryByRole("article")).toBeNull();
});

test("bundled SVG diagram is sanitized; remote assets and raw HTML never become active", () => {
  const { container } = render(<SkillOverview snapshot={snapshot} />);
  fireEvent.click(screen.getByRole("button", { name: "Read full overview" }));
  const image = screen.getByRole("img", { name: "Flow" });
  const svg = decodeURIComponent(image.getAttribute("src")!.split(",")[1]);
  expect(svg).toContain("Read then propose");
  expect(svg).not.toMatch(/script|foreignObject|external.invalid|href=/i);
  expect(container.querySelector("script")).toBeNull();
  expect(container.querySelector('img[src^="https:"]')).toBeNull();
  expect(screen.getByText("[Image unavailable: Remote]")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Details" }));
  expect(screen.getByRole("img", { name: "Diagram" })).toHaveAttribute("src", image.getAttribute("src"));
  fireEvent.click(screen.getByRole("button", { name: "Back to overview" }));
  expect(screen.getByRole("heading", { name: "How it works" })).toBeInTheDocument();
});

test("fallback uses pinned SKILL.md when no optional overview exists", () => {
  render(<SkillOverview snapshot={{ ...snapshot, files: [snapshot.files[0]] }} />);
  fireEvent.click(screen.getByRole("button", { name: "Read full overview" }));
  expect(screen.getByTestId("skill-full-overview")).toHaveTextContent("Use the selected PR.");
  expect(screen.getByTestId("skill-full-overview")).not.toHaveTextContent("description:");
});

test("literal and folded descriptions become one sentence; relative paths stay inside bundle", () => {
  expect(skillDescription('---\ndescription: >\n  Read the PR and\n  propose a title. More.\nname: skill\n---\n# Body').summary).toBe("Read the PR and propose a title.");
  expect(bundlePath("references/how.md", "../assets/flow.svg")).toBe("assets/flow.svg");
  for (const target of ["../../secret", "https://example.org/a", "data:image/png,abc", "/private", "%2e%2e/secret", "bad\\path"]) expect(bundlePath("OVERVIEW.md", target)).toBeNull();
});

test("verified raster data renders, arbitrary image URL does not", () => {
  const png = "data:image/png;base64,iVBORw0KGgo=";
  render(<SkillOverview snapshot={{ ...snapshot, files: [snapshot.files[0], textFile("OVERVIEW.md", "![Raster](image.png)"), { ...textFile("image.png", ""), kind: "binary", text: null, image_data_url: png }] }} />);
  fireEvent.click(screen.getByRole("button", { name: "Read full overview" }));
  expect(screen.getByRole("img", { name: "Raster" })).toHaveAttribute("src", png);
});
