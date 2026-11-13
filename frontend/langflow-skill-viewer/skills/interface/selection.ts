/** Inspection is available only for the currently resolved source/skill/revision. */
export function inspectionSelection(template: unknown): { skillId: string; revision: string; privateSelection?: { connectionId: string; repositoryId: number } } {
  const fields = (template && typeof template === "object" ? template : {}) as Record<string, unknown>;
  const value = (name: string): string => {
    const field = fields[name];
    if (!field || typeof field !== "object") return "";
    const selected = (field as { value?: unknown }).value;
    return typeof selected === "string" ? selected : "";
  };
  if (value("github_connection")) {
    const privateSelection = { connectionId: value("github_connection"), repositoryId: Number(value("private_repository_id")) };
    try {
      const captured = JSON.parse(value("resolved_selection"));
      const current = [value("source"), value("skill_id"), value("revision_id"), value("github_connection")];
      if (!Array.isArray(captured) || captured.length !== 4 || captured.some((entry, i) => entry !== current[i])) throw new Error("selection_changed");
      return { skillId: value("resolved_skill_id"), revision: value("resolved_revision_id"), privateSelection };
    } catch { return { skillId: "", revision: "", privateSelection }; }
  }
  if (!value("source")) return { skillId: value("skill_id"), revision: value("revision_id") };
  try {
    const captured = JSON.parse(value("resolved_selection"));
    const current = [value("source"), value("skill_id"), value("revision_id")];
    if (!Array.isArray(captured) || captured.length !== 3 || captured.some((v, i) => v !== current[i])) {
      return { skillId: "", revision: "" };
    }
    return { skillId: value("resolved_skill_id"), revision: value("resolved_revision_id") };
  } catch {
    return { skillId: "", revision: "" };
  }
}
