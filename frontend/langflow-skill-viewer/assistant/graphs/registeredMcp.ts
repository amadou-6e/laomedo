export function isRegisteredMcpNode(data: unknown): boolean {
  if (!data || typeof data !== "object") return false;
  const node = data as {
    type?: unknown;
    laomedo_authoring_bindings?: { resources?: { kind?: unknown }[] };
  };
  return (
    typeof node.type === "string" &&
    (node.type === "MCPTools" || node.type.endsWith("/MCPTools")) &&
    Array.isArray(node.laomedo_authoring_bindings?.resources) &&
    node.laomedo_authoring_bindings.resources.some((item) => item?.kind === "mcp")
  );
}
