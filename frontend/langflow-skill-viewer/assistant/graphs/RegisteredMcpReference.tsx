export default function RegisteredMcpReference({
  value,
  labelledBy,
}: {
  value: unknown;
  labelledBy?: string;
}) {
  const selected = value && typeof value === "object" ? (value as { name?: unknown }).name : null;
  return (
    <input
      readOnly
      value={typeof selected === "string" ? selected : ""}
      aria-label={labelledBy ? undefined : "Registered MCP server"}
      aria-labelledby={labelledBy}
      className="w-full rounded-md border border-input bg-transparent px-3 py-2 text-sm"
    />
  );
}
