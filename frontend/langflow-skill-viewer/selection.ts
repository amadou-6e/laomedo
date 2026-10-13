/** Inspection is available only for the currently resolved source/skill/revision. */
export function inspectionSelection(template: unknown): { skillId: string; revision: string } {
  const fields = (template && typeof template === "object" ? template : {}) as Record<string, unknown>;
  const value = (name: string): string => {
    const field = fields[name];
    if (!field || typeof field !== "object") return "";
    const selected = (field as { value?: unknown }).value;
    return typeof selected === "string" ? selected : "";
  };
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
