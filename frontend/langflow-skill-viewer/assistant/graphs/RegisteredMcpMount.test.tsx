import { renderHook } from "@testing-library/react";
import useFetchDataOnMount from "@/CustomNodes/hooks/use-fetch-data-on-mount";
import { mutateTemplate } from "@/CustomNodes/helpers/mutate-template";

let mockNodes: unknown[] = [];

jest.mock("@/stores/flowStore", () => ({
  __esModule: true,
  default: { getState: () => ({ nodes: mockNodes }) },
}));
jest.mock("@/stores/alertStore", () => ({
  __esModule: true,
  default: (select: (state: unknown) => unknown) => select({ setErrorData: jest.fn() }),
}));
jest.mock("@/CustomNodes/helpers/mutate-template", () => ({ mutateTemplate: jest.fn() }));

describe("registered MCP native input mount", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockNodes = [];
  });

  it.each(["mcp_server", "tools_metadata"])("does not refresh pinned %s on mount", (name) => {
    mockNodes = [{ id: "tools", data: {
      type: "MCPTools",
      laomedo_authoring_bindings: { resources: [{ kind: "mcp" }] },
    } }];
    const node = { tool_mode: true, template: {
      [name]: { value: { name: "Local echo" }, real_time_refresh: true },
    } } as unknown as Parameters<typeof useFetchDataOnMount>[0];
    renderHook(() => useFetchDataOnMount(node, "tools", jest.fn(), name, {} as never));
    expect(mutateTemplate).not.toHaveBeenCalled();
  });

  it.each(["MCPTools", "Other"])("preserves native refresh for an unpinned or unrelated %s", (type) => {
    mockNodes = [{ id: "tools", data: {
      type,
      ...(type === "Other" ? { laomedo_authoring_bindings: { resources: [{ kind: "mcp" }] } } : {}),
    } }];
    const node = { tool_mode: true, template: {
      mcp_server: { value: { name: "Local echo" }, real_time_refresh: true },
    } } as unknown as Parameters<typeof useFetchDataOnMount>[0];
    renderHook(() => useFetchDataOnMount(node, "tools", jest.fn(), "mcp_server", {} as never));
    expect(mutateTemplate).toHaveBeenCalledTimes(1);
  });
});
