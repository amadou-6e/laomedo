import { fireEvent, render, screen } from "@testing-library/react";
import RegisteredMcpReference from "./RegisteredMcpReference";
import { isRegisteredMcpNode } from "./registeredMcp";

describe("registered MCP canvas reference", () => {
  it("preserves the selected name without discovery or management controls", () => {
    const selection = Object.freeze({ name: "Local echo" });
    const { rerender } = render(<RegisteredMcpReference value={selection} />);
    const input = screen.getByRole("textbox", { name: "Registered MCP server" });
    expect(input).toHaveAttribute("readonly");
    expect(input).toHaveValue("Local echo");
    fireEvent.click(input);
    rerender(<RegisteredMcpReference value={selection} />);
    expect(input).toHaveValue("Local echo");
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(selection).toEqual({ name: "Local echo" });
  });

  it("does not interpret configuration objects or markup as a server name", () => {
    const { rerender } = render(<RegisteredMcpReference value={{ name: { token: "hidden" } }} />);
    expect(screen.getByRole("textbox")).toHaveValue("");
    rerender(<RegisteredMcpReference value={{ name: "<b>echo</b>" }} />);
    expect(screen.getByRole("textbox")).toHaveValue("<b>echo</b>");
    expect(screen.queryByText("echo")).not.toBeInTheDocument();
  });

  it("leaves ordinary MCP widgets and other resource nodes unchanged", () => {
    const binding = { resources: [{ kind: "mcp" }] };
    expect(isRegisteredMcpNode({ type: "MCPTools", laomedo_authoring_bindings: binding })).toBe(true);
    expect(isRegisteredMcpNode({ type: "laomedo/MCPTools", laomedo_authoring_bindings: binding })).toBe(true);
    expect(isRegisteredMcpNode({ type: "MCPTools" })).toBe(false);
    expect(isRegisteredMcpNode({ type: "Other", laomedo_authoring_bindings: binding })).toBe(false);
    expect(isRegisteredMcpNode({ type: "MCPTools", laomedo_authoring_bindings: { resources: "invalid" } })).toBe(false);
  });
});
