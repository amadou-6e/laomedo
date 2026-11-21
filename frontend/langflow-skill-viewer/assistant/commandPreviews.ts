/** Documentation previews, not a native capability catalog or execution grant. */
export const codexCommandPreviews = [
  { name: "plan", description: "Toggle native plan mode." },
  { name: "status", description: "Start a session without using the model." },
  { name: "mcp", description: "Show configured MCP tools." },
  { name: "skills", description: "List available skills." },
  { name: "review", description: "Request a review." },
  { name: "review-branch", description: "Review changes relative to a base branch." },
  { name: "review-commit", description: "Review a specific commit." },
  { name: "compact", description: "Compact the conversation context." },
  { name: "goal", description: "Manage a native continuation goal." },
  { name: "rename", description: "Rename the native session." },
  { name: "logout", description: "Sign out of the native account." },
];

/** Pinned adapter built-ins only; actual session advertisement still governs admission. */
export const providerCommandPreviews: Record<string, typeof codexCommandPreviews> = {
  codex: codexCommandPreviews,
  claude: [
    {name: "compact", description: "Compact the conversation context."},
    {name: "usage", description: "Show native usage and limits."},
    {name: "context", description: "Show native context usage."},
    {name: "mcp", description: "Show native MCP connection status."},
  ],
  opencode: [
    {name: "init", description: "Create workspace agent instructions."},
    {name: "review", description: "Review workspace changes."},
  ],
};

/** AP-2 candidate names are reserved for native admission, never chat fallback. */
export const providerCommandNames: Record<string, readonly string[]> = {
  codex: codexCommandPreviews.map(item => item.name),
  claude: ["compact", "usage", "context", "mcp", "init", "review", "security-review", "code-review", "status", "help", "plan", "model", "effort", "agents", "permissions", "clear", "rename", "logout", "login", "cost", "doctor", "todos", "resume", "export", "copy", "memory", "debug", "new", "rewind", "config"],
  opencode: ["init", "review", "compact"],
};
