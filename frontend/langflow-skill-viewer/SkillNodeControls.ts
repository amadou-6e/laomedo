/** Presentation policy also applies to old saved templates; never mutates values. */
const SETTINGS = new Set(["revision_id", "commit_id"]);
const HELP: Record<string, string> = {
  source: "Public HTTPS GitHub/GitLab repository URL, or a local folder allowed by the host source service. Leave empty to use a saved registry reference.",
  revision_id: "The exact file version to use. Choose a discovered revision; refreshing never selects a newer version.",
  discovery_status: "Scans Source and lists available skills and revisions. Reads and imports files; never runs a Skill or changes the selected revision.",
  operation: "Receive file changes from another node. Creates one revision for the batch; publish it in Skill files when ready.",
};

export function isSkillNode(data: any): boolean {
  return (data.node?.name || data.node?.type || data.type) === "LaomedoSkill";
}

export function isSkillControlHidden(data: any, name: string): boolean {
  return isSkillNode(data) && ["edit_request", "discovery_status"].includes(name);
}

export const SKILL_SOURCE_ERROR_CODE = "source_discovery_failed";

/** Only fixed, safe failure messages belong below Source; empty results stay quiet. */
export function skillSourceError(data: any): string | undefined {
  if (!isSkillNode(data) || !String(data.node?.template?.source?.value || "").trim()) return;
  const status = data.node?.template?.discovery_status?.value;
  return status === "Discovery failed. Check source access and refresh." ? status : undefined;
}

export function skillChoicePlaceholder(data: any, name: string, fallback?: string): string | undefined {
  if (!data || !isSkillNode(data) || name !== "skill_id") return fallback;
  const template = data.node?.template;
  return String(template?.source?.value || "").trim() && template?.skill_id?.options?.length
    ? "Select an option" : "No source found";
}

export function isConnectedSkillSetting(data: any, name: string, edges: any[]): boolean {
  return isSkillNode(data) && SETTINGS.has(name) && edges.some(edge =>
    edge.target === data.id && edge.data?.targetHandle?.fieldName === name);
}

export function advancedSkillFields(data: any, fields: string[], edges: any[], toolMode: boolean): string[] {
  if (!isSkillNode(data)) return [];
  return fields.filter(name => {
    const field = data.node?.template?.[name];
    return SETTINGS.has(name) && field?.show && field.type !== "other" &&
      !(toolMode && field.tool_mode) && !isConnectedSkillSetting(data, name, edges);
  });
}

export function skillFieldInfo(data: any, name: string): string {
  return (isSkillNode(data) && HELP[name] ? HELP[name] : data.node?.template?.[name]?.info) || "";
}

export function skillNodeDescription(data: any): string | undefined {
  const description = data.node?.description;
  return isSkillNode(data) && description === "Read an immutable skill or propose a traceable, atomic multi-file revision."
    ? "Use and edit versioned skill files." : description;
}
