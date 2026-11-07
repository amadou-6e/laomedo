/** GitHub PR presentation, including saved templates. Never rewrites saved values. */
const ORDER = ["repository_url", "state", "labels", "pr_choice", "pr_context"];
export const PR_DISCOVERY_ERROR = "GitHub discovery failed. Check connection and refresh.";
export const PR_DISCOVERY_ERROR_CODE = "pr_discovery_failed";

export function isPRNode(data: any): boolean {
  const kind = data?.node?.name || data?.node?.type || data?.type || "";
  return (kind.match(/^ext:[^:]+:([^@]+)@.+$/)?.[1] ?? kind) === "LaomedoGitHubPR";
}

export function isPRControlHidden(data: any, name: string): boolean {
  return isPRNode(data) && name === "discovery_status";
}

export function prFieldRank(data: any, name: string): number {
  const rank = ORDER.indexOf(name);
  return isPRNode(data) && rank >= 0 ? rank : ORDER.length;
}

export function isVisiblePRState(data: any, name: string, toolMode: boolean): boolean {
  const field = data.node?.template?.[name];
  return isPRNode(data) && name === "state" && field?.show && !(toolMode && field.tool_mode);
}

export function prFieldTemplate(data: any, name: string, field: any): any {
  if (!isPRNode(data)) return field;
  if (name === "state") return { ...field, advanced: false, options: ["open", "closed", "merged", "all"] };
  if (["labels", "pr_choice"].includes(name)) return { ...field, combobox: false };
  return field;
}

/** Never render arbitrary saved/provider text as connection feedback. */
export function prFeedback(data: any): { message: string; error: boolean } | undefined {
  if (!isPRNode(data) || !String(data.node?.template?.repository_url?.value || "").trim()) return;
  const value = data.node?.template?.discovery_status?.value;
  if (value === PR_DISCOVERY_ERROR) return { message: value, error: true };
  if (["Discovering GitHub PRs...", "No matching PRs."].includes(value)) return { message: value, error: false };
}

export function prChoicePlaceholder(data: any, name: string, fallback?: string): string | undefined {
  if (!isPRNode(data) || !["labels", "pr_choice"].includes(name)) return fallback;
  const template = data.node?.template;
  if (!String(template?.repository_url?.value || "").trim()) return "Enter repository URL";
  const status = template?.discovery_status?.value;
  if (status === PR_DISCOVERY_ERROR) return "Connection unavailable";
  if (status === "Discovering GitHub PRs...") return name === "labels" ? "Loading labels..." : "Loading PRs...";
  if (!template?.[name]?.options?.length) return name === "labels" ? "No labels available" : "No matching PRs.";
  return name === "labels" ? "Select labels" : "Select a PR";
}
