/** GitHub PR presentation, including saved templates. Never rewrites saved values. */
const ORDER = ["repository_url", "state", "labels", "pr_choice", "pr_context"];
export const PR_DISCOVERY_ERROR = "GitHub discovery failed. Check connection and refresh.";
export const PR_DISCOVERY_ERROR_CODE = "pr_discovery_failed";

/** Filter already discovered PRs by title/number and state:/label: qualifiers. */
export function filterPRChoices(query: string, options: string[], metadata: any[]): string[] {
  const tokens = query.match(/(?:[^\s"]|"[^"]*")+/g) ?? [];
  return options.filter((option) => {
    const item = metadata.find((entry) => entry?.id === option && entry?.laomedo_pr_search === true);
    if (!item) return false;
    return tokens.every((token) => {
      const match = token.match(/^(state|label):(.+)$/i);
      if (!match) return option.toLowerCase().includes(token.toLowerCase());
      const value = match[2].replace(/^"(.*)"$/, "$1").toLowerCase();
      if (match[1].toLowerCase() === "state") return value === "all" || item.state === value || (value === "closed" && item.state === "merged");
      return Array.isArray(item.labels) && item.labels.some((label: string) => label.toLowerCase() === value);
    });
  });
}

export function isPRNode(data: any): boolean {
  const kind = data?.node?.name || data?.node?.type || data?.type || "";
  return (kind.match(/^ext:[^:]+:([^@]+)@.+$/)?.[1] ?? kind) === "LaomedoGitHubPR";
}

export function isPRControlHidden(data: any, name: string): boolean {
  return isPRNode(data) && (["discovery_status", "state", "labels", "github_connection"].includes(name) || (name === "pr_choice" && !!data?.node?.template?.github_connection?.value));
}

export function prFieldRank(data: any, name: string): number {
  const rank = ORDER.indexOf(name);
  return isPRNode(data) && rank >= 0 ? rank : ORDER.length;
}

export function isVisiblePRState(data: any, name: string, toolMode: boolean): boolean {
  return false;
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
/** Admit only the declared two-node PR/Agent feedback topology in the canvas.
 * The backend still validates input scope, identity and every write grant.
 */
export function isPRFeedbackConnection(connection: any, nodes: any[], edges: any[], parse: (value: string) => any): boolean {
  try {
    const source = parse(connection.sourceHandle);
    const target = parse(connection.targetHandle);
    const sourceNode = nodes.find(node => node.id === connection.source);
    const targetNode = nodes.find(node => node.id === connection.target);
    const agent = (node: any) => ["LaomedoCodexAgent", "LaomedoClaudeAgent", "LaomedoOpenCodeAgent"].includes(
      String(node?.data?.node?.name || node?.data?.type || "").replace(/^ext:[^:]+:([^@]+)@.+$/, "$1"));
    const forward = isPRNode(sourceNode?.data) && source.name === "pr" && agent(targetNode) && target.fieldName === "task";
    const backward = agent(sourceNode) && source.name === "answer" && isPRNode(targetNode?.data) && target.fieldName === "pr_context";
    if (!forward && !backward) return false;
    return edges.filter(edge => edge.source === connection.target && edge.target === connection.source).some(edge => {
      const from = parse(edge.sourceHandle), to = parse(edge.targetHandle);
      return forward ? from.name === "answer" && to.fieldName === "pr_context" : from.name === "pr" && to.fieldName === "task";
    });
  } catch { return false; }
}
