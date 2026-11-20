/** Documentation previews, not a native capability catalog or execution grant. */
export const codexCommandPreviews = [
  { name: "status", description: "Start a session without using the model." },
  { name: "mcp", description: "Show configured MCP tools." },
  { name: "skills", description: "List available skills." },
  { name: "review", description: "Request a review." },
  { name: "compact", description: "Compact the conversation context." },
];

/** AP-2 candidate names are reserved for native admission, never chat fallback. */
export const providerCommandNames: Record<string, readonly string[]> = {
  codex: codexCommandPreviews.map(item => item.name),
  claude: ["compact"],
  opencode: ["init", "review", "compact"],
};
