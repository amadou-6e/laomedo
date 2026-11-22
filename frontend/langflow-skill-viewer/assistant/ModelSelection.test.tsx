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
