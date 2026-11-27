import useFlowStore, { syncNodeTranslations } from "@/stores/flowStore";

let mockDefinition: unknown;
jest.mock("@/stores/typesStore", () => ({
  __esModule: true,
  useTypesStore: { getState: () => ({
    data: { tools: { MCPTools: mockDefinition } },
    types: { MCPTools: "tools" },
    templates: {},
    componentDisplayNames: {},
  }) },
}));

describe("registered MCP output translations", () => {
  it.each([true, false])("keeps output identity when pinned=%s", (pinned) => {
    mockDefinition = {
      template: {},
      outputs: [
        { name: "response", display_name: "Response" },
        { name: "component_as_tool", display_name: "Toolset" },
      ],
    };
    const output = { name: "component_as_tool", display_name: "Toolset", types: ["Tool"] };
    const node = { id: "mcp", type: "genericNode", data: {
      id: "mcp", type: "MCPTools", node: { template: {}, outputs: [output] },
      ...(pinned ? { laomedo_authoring_bindings: { resources: [{ kind: "mcp" }] } } : {}),
    } };
    useFlowStore.setState({ nodes: [node] as never });
    syncNodeTranslations();
    const actual = useFlowStore.getState().nodes[0].data.node!.outputs![0];
    expect(actual).toEqual({ ...output, display_name: pinned ? "Toolset" : "Response" });
    expect(output.display_name).toBe("Toolset");
  });

  it("preserves a pinned output absent from the current template", () => {
    mockDefinition = { template: {}, outputs: [{ name: "response", display_name: "Response" }] };
    const output = { name: "component_as_tool", display_name: "Toolset", types: ["Tool"] };
    useFlowStore.setState({ nodes: [{ id: "mcp", type: "genericNode", data: {
      id: "mcp", type: "MCPTools", node: { template: {}, outputs: [output] },
      laomedo_authoring_bindings: { resources: [{ kind: "mcp" }] },
    } }] as never });
    syncNodeTranslations();
    expect(useFlowStore.getState().nodes[0].data.node!.outputs![0]).toEqual(output);
  });
});
