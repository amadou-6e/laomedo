import { fireEvent, render, screen } from "@testing-library/react";
import SkillViewerProvider, { SkillViewerRequest } from "./SkillViewer";

jest.mock("./SkillFilesModal", () => ({ __esModule: true, default: ({ skillId, revision, setOpen }: any) => {
  const [text, setText] = require("react").useState("");
  return <div role="dialog" aria-label={`${skillId}:${revision}`}>
    <input aria-label="Working text" value={text} onChange={(event) => setText(event.target.value)} />
    <button onClick={() => setOpen(false)}>Close workspace</button>
  </div>;
} }));

test("toolbar removal and a new request preserve the active workspace and its working state", async () => {
  const acknowledge = jest.fn();
  const view = render(<SkillViewerProvider><SkillViewerRequest open setOpen={acknowledge} skillId="first" revision="exact-one" /></SkillViewerProvider>);
  await screen.findByRole("dialog", { name: "first:exact-one" });
  expect(acknowledge).toHaveBeenCalledWith(false);
  fireEvent.change(screen.getByRole("textbox", { name: "Working text" }), { target: { value: "unsaved text" } });
  view.rerender(<SkillViewerProvider>{null}</SkillViewerProvider>);
  expect(screen.getByRole("textbox", { name: "Working text" })).toHaveValue("unsaved text");
  view.rerender(<SkillViewerProvider><SkillViewerRequest open setOpen={acknowledge} skillId="second" revision="exact-two" /></SkillViewerProvider>);
  expect(screen.getByRole("dialog", { name: "first:exact-one" })).toBeVisible();
  expect(screen.getByRole("textbox", { name: "Working text" })).toHaveValue("unsaved text");
  fireEvent.click(screen.getByRole("button", { name: "Close workspace" }));
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("leaving the authenticated owner releases the in-memory workspace", async () => {
  const acknowledge = jest.fn();
  const view = render(<SkillViewerProvider><SkillViewerRequest open setOpen={acknowledge} skillId="first" revision="exact-one" /></SkillViewerProvider>);
  await screen.findByRole("dialog");
  view.unmount();
  render(<SkillViewerProvider>{null}</SkillViewerProvider>);
  expect(screen.queryByRole("dialog")).toBeNull();
});
