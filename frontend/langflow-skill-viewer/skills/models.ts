/** Immutable registry wire records shared by Skill views. */
export type Commit = { commit_id: string; parent_commit: string | null; revision_id: string;
  message: string; created_at: string; editor: Record<string, string>; policy_ref?: Record<string, string> };
export type History = { skill_id: string; selected_revision: string; commits: Commit[]; next: string | null };
export type SkillFile = { path: string; bytes: number; file_hash: string; kind: "text" | "binary"; text: string | null; image_data_url?: string; binary_base64?: string };
export type Snapshot = { schema_version: string; skill_id: string; revision_id: string; tree_hash: string; files: SkillFile[] };
