import { fireEvent, render, screen } from "@testing-library/react";
import SkillActions, { dismissSkillActions } from "./SkillActions";

test("Escape closes actions and returns focus without propagating to the dialog", () => {
  const escape = jest.fn();
  render(<div onKeyDown={escape}><SkillActions label="Section actions"><button>Action</button></SkillActions></div>);
  const trigger = screen.getByLabelText("Section actions");
  fireEvent.click(trigger);
  const action = screen.getByRole("button", { name: "Action" });
  action.focus();
  fireEvent.keyDown(action, { key: "Escape" });
  expect(action).not.toBeVisible();
  expect(trigger).toHaveFocus();
  expect(escape).not.toHaveBeenCalled();
});

test("outside pointer and leaving the actions close the disclosure", () => {
  render(<><SkillActions label="Section actions"><button>Action</button></SkillActions><button>Outside</button></>);
  const trigger = screen.getByLabelText("Section actions");
  fireEvent.click(trigger);
  fireEvent.pointerDown(screen.getByRole("button", { name: "Outside" }));
  expect(trigger.closest("details")).not.toHaveAttribute("open");
  expect(screen.getByText("Action")).not.toBeVisible();
  fireEvent.click(trigger);
  fireEvent.blur(trigger, { relatedTarget: screen.getByRole("button", { name: "Outside" }) });
  expect(trigger.closest("details")).not.toHaveAttribute("open");
  expect(screen.getByText("Action")).not.toBeVisible();
});


test("the native dialog listener still sees Escape as consumed after React closes actions", () => {
  render(<SkillActions label="Section actions"><button>Action</button></SkillActions>);
  fireEvent.click(screen.getByLabelText("Section actions"));
  const action = screen.getByRole("button", { name: "Action" });
  const event = new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true });
  action.dispatchEvent(event);
  expect(dismissSkillActions(event)).toBe(true);
  expect(action).not.toBeVisible();
});
