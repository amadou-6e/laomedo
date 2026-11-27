/** Local account selection is always omitted, even when exporting API keys. */
export function stripLocalBindings(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stripLocalBindings);
  if (!value || typeof value !== "object") return value;
  const result = Object.fromEntries(Object.entries(value).map(([key, item]) => [key, stripLocalBindings(item)]));
  if (result.provider_connection && typeof result.provider_connection === "object" && !Array.isArray(result.provider_connection))
    result.provider_connection = { ...result.provider_connection, value: "", options: [], options_metadata: [] };
  return result;
}
