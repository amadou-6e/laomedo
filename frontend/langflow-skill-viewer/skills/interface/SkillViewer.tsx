import { createContext, lazy, Suspense, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

const SkillFilesModal = lazy(() => import("../workspace/SkillFilesModal"));
type Selection = { skillId: string; revision: string };
const SkillViewerContext = createContext<((selection: Selection) => void) | null>(null);

/** Own the workspace above canvas/toolbars; reconnecting must not discard edits. */
export default function SkillViewerProvider({ children }: { children: ReactNode }) {
  const [selection, setSelection] = useState<Selection | null>(null);
  const request = useCallback((next: Selection) => setSelection((current) => current || next), []);
  return <SkillViewerContext.Provider value={request}>
    {children}
    <Suspense fallback={<div role="status">Loading Skill files...</div>}>
      {selection && <SkillFilesModal open skillId={selection.skillId} revision={selection.revision}
        setOpen={(value) => { if (!value) setSelection(null); }} />}
    </Suspense>
  </SkillViewerContext.Provider>;
}

/** Capture the exact requested identity, then release the transient toolbar. */
export function SkillViewerRequest({ open, setOpen, skillId, revision }: Selection & {
  open: boolean; setOpen: (value: boolean) => void;
}) {
  const request = useContext(SkillViewerContext);
  useEffect(() => {
    if (!open || !request) return;
    request({ skillId, revision });
    setOpen(false);
  }, [open, request, revision, setOpen, skillId]);
  return null;
}
