import { fireEvent, render, screen } from "@testing-library/react";
import ModelSelection from "./ModelSelection";

test("selects a model through its native radio without changing effort or dispatching", () => {
  const select = jest.fn();
  const effort = jest.fn();
  render(<ModelSelection models={{provider: "opencode", models: [{id: "first", efforts: ["default"]}, {id: "second", efforts: ["default"]}]}} model="first" effort="default" disabled={false} onModel={select} onEffort={effort} />);
  fireEvent.click(screen.getByRole("button", {name: "Choose model and effort"}));
  expect(screen.getByRole("radio", {name: "first"})).toBeChecked();
  fireEvent.click(screen.getByRole("radio", {name: "second"}));
  expect(select).toHaveBeenCalledWith("second");
  expect(effort).not.toHaveBeenCalled();
});

test("hides OpenCode Go display prefixes while preserving the exact model identity", () => {
  const select=jest.fn();
  render(<ModelSelection models={{provider:"opencode",models:[{id:"opencode-go/gpt-6-luna",efforts:["default"]}]}} model="opencode-go/gpt-6-luna" effort="default" disabled={false} onModel={select} onEffort={jest.fn()} />);
  expect(screen.getByText("gpt-6-luna")).toBeVisible();
  fireEvent.click(screen.getByRole("button",{name:"Choose model and effort"}));
  fireEvent.click(screen.getByRole("radio",{name:"opencode-go/gpt-6-luna"}));
  expect(screen.getByRole("radio",{name:"opencode-go/gpt-6-luna"})).toBeChecked();
});
