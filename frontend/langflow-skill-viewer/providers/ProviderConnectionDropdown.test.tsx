import { fireEvent, render, screen } from "@testing-library/react";
import { DropdownOptionsList } from "@/components/core/dropdownComponent/components/DropdownOptionsList";
import { DropdownTrigger } from "@/components/core/dropdownComponent/components/DropdownTrigger";
import { stripLocalBindings } from "./exports";

jest.mock("@/CustomNodes/GenericNode/components/NodeDialogComponent", () => ({ __esModule: true, default: () => null }));
jest.mock("@/components/common/genericIconComponent", () => ({ __esModule: true, default: () => null }));
jest.mock("@/components/common/loadingTextComponent", () => ({ __esModule: true, default: () => null }));
jest.mock("@/components/common/shadTooltipComponent", () => ({ __esModule: true, default: ({ children }) => <>{children}</> }));
jest.mock("@/components/ui/command", () => ({
  CommandGroup: ({ children }) => <div>{children}</div>, CommandList: ({ children }) => <div>{children}</div>,
  CommandSeparator: () => null, CommandItem: ({ children, onSelect, value, ...props }) => <button {...props} onClick={() => onSelect?.(value)}>{children}</button>,
}));
jest.mock("@/components/ui/button", () => ({ Button: ({ children, ...props }) => <button {...props}>{children}</button> }));
jest.mock("@/components/ui/popover", () => ({ PopoverTrigger: ({ children }) => <>{children}</> }));
jest.mock("@/utils/utils", () => ({ cn: (...items) => items.filter(x => typeof x === "string").join(" ") }));
jest.mock("@/utils/stringManipulation", () => ({ getStatusColor: () => "", convertStringToHTML: value => value }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: key => key }) }));

const id = "00000000-0000-4000-8000-000000000001";
const metadata = [{ id, display_name: "Work account", laomedo_connection: true }];

test("account choice shows only the label and submits its opaque ID", () => {
  const select = jest.fn();
  render(<DropdownOptionsList {...({ filteredOptions: [id], filteredMetadata: metadata, firstWord: "Connection", value: "", onSelect: select, setOpen: jest.fn(), setWaitingForResponse: jest.fn(), sourceOptions: {}, handleSourceOptions: jest.fn(), handleRefreshButtonPress: jest.fn(), openDialog: false, setOpenDialog: jest.fn(), setPendingSelect: jest.fn() } as any)} />);
  expect(screen.getByText("Work account")).toBeVisible();
  expect(screen.queryByText(/display_name|laomedo_connection/)).toBeNull();
  fireEvent.click(screen.getByTestId(`${id}-0-option`));
  expect(select).toHaveBeenCalledWith(id, undefined, undefined, metadata[0]);
});

test("closed account selector shows its label without exposing the local ID", () => {
  render(<DropdownTrigger {...({ validOptions: [id], open: false, id: "connection", value: id, options: [id], filteredOptions: [id], filteredMetadata: metadata, refButton: { current: null } } as any)} />);
  expect(screen.getByRole("combobox")).toHaveTextContent("Work account");
  expect(screen.getByRole("combobox")).not.toHaveTextContent(id);
});

test("portable download omits the local choice and account options", () => {
  const original = { template: { provider_connection: { value: id, options: [id], options_metadata: metadata }, task: { value: "Do work" } } };
  const portable = stripLocalBindings(original) as typeof original;
  expect(portable.template.provider_connection).toEqual({ value: "", options: [], options_metadata: [] });
  expect(original.template.provider_connection.value).toBe(id);
  expect(portable.template.task.value).toBe("Do work");
});
