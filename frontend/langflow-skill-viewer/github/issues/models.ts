export type Issue = { repository: string; number: number; url: string; title: string; body: string; state: string; labels: string[]; updated_at: string };
export type Snapshot = { schema_version: string; issue: Issue; fetched_at: string };
