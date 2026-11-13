import type { Snapshot } from "../models";

export type PrivateSelection = { connectionId: string; repositoryId: number };
export type PrivateOrigin = { owner_id: string; connection_id: string; repository_id: number;
  choice: { choice: string; name: string; path: string }; skill_id: string; revision_id: string; commit: string; label: string };
export type PrivateDiscovery = { skills: { choice: string; name: string; path: string }[] };
export type PrivateSnapshot = Snapshot;
