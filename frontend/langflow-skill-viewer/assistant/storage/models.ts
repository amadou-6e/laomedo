export type RepositoryLocation = { repository_id: string; path: string };
export type RepositoryConnection = { id: string; name: string; path: string };
export type StoredGraph = { location: RepositoryLocation; sha256: string; current_sha256: string | null; availability: string };
export type ProjectStorageState = {
  repositories: RepositoryConnection[];
  agent_files: RepositoryLocation | null;
  graphs: Record<string, StoredGraph>;
  workflows: { id: string; name: string; revision: string }[];
};
