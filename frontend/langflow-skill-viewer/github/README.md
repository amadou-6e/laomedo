# GitHub frontend

`issues/` and `pull_requests/` own identity-preserving read-only viewers. Each leaf separates wire models, selection/link helpers and rendering. The leaf index is the upstream modal interface. `models.ts` owns the graph-node template shape; inspection snapshots remain feature-owned. Deployment preserves this tree under modals/github.

`interface/` owns read-error admission and shared descriptive presentation. The installer deploys this whole feature tree; viewers do not depend on Skill-owned modules.
