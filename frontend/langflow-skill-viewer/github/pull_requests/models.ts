export type PR = { repository: string; number: number; url: string; title: string; body: string; state: string; labels: string[]; updated_at: string; draft: boolean; merged: boolean; head: {branch: string; sha: string}; base: string };
export type Snapshot = { schema_version: string; pr: PR; fetched_at: string };
