/** Graph-node fields consumed by GitHub viewer selection adapters. */
import type { VertexBuildTypeAPI } from "@/types/api";

export type NodeTemplate = Record<string, { value?: unknown }> | undefined;

/** Only the executed graph records needed to project a GitHub outcome. */
export type GitHubBuildState = {
  nodes: { id: string; data?: { type?: string } }[];
  flowPool: Record<string, VertexBuildTypeAPI[]>;
};
