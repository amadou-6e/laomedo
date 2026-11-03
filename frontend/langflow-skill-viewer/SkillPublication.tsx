import { useEffect, useMemo, useState } from "react";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";
import type { SkillFile, Snapshot } from "./SkillHistory";

// Disclose the whole working tree, including saved unpublished commits, without
// introducing a second publication mode.
export function useRegistryComparison(skillId: string, latest: string, files: SkillFile[]) {
  const [base, setBase] = useState<Snapshot | null>(null);
  const [failed, setFailed] = useState(false);
  const [showError, setShowError] = useState(false);
  const [reload, setReload] = useState(0);
  useEffect(() => {
    const controller = new AbortController(); setBase(null); setFailed(false);
    if (!latest) return () => controller.abort();
    api.get<Snapshot>(`${getBaseUrl()}laomedo/skills/${encodeURIComponent(skillId)}/${encodeURIComponent(latest)}`, { signal: controller.signal }).then(({ data }) => {
      if (controller.signal.aborted) return;
      if (data.schema_version !== "laomedo.skill-inspection.v1" || data.skill_id !== skillId || data.revision_id !== latest || data.tree_hash !== latest) throw Error();
      setBase(data);
    }).catch(() => { if (!controller.signal.aborted) { setFailed(true); setShowError(true); } });
    return () => controller.abort();
  }, [skillId, latest, reload]);
  const paths = useMemo(() => [...new Set([...(base?.files || []).map((file) => file.path), ...files.map((file) => file.path)])].sort()
    .filter((path) => {
      const before = base?.files.find((file) => file.path === path), after = files.find((file) => file.path === path);
      return !before || !after || (before.kind === "text" && after.kind === "text" ? before.text !== after.text : before.file_hash !== after.file_hash);
    }), [base, files]);
  return { base: base?.revision_id === latest ? base : null, paths, failed, showError,
    retry: () => { setShowError(false); setReload((value) => value + 1); }, dismissError: () => setShowError(false) };
}
