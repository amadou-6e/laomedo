import { fireEvent, render, screen } from "@testing-library/react";
import SkillActions from "./SkillActions";

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
