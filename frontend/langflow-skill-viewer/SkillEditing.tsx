import { useEffect, useMemo, useRef, useState } from "react";
import { v4 as uuid } from "uuid";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";
import type { Snapshot } from "./SkillHistory";

export type SkillEditorState = { skill_id: string; selected_revision: string; head_revision: string; head_commit: string;
  latest_revision: string; can_edit: boolean; can_publish: boolean; edit_enabled: boolean };
type SaveResult = { skill: { skill_id: string; revision_id: string; tree_hash: string }; commit: { commit_id: string } };
type Pending = { action: "save" | "publish"; body: Record<string, unknown> };
const manualUrl = (action: string) => `${getBaseUrl()}laomedo/skills/manual/${action}`;

export function useSkillEditing(skillId: string, revision: string, snapshot: Snapshot | null, onSaved: (revision: string) => void) {
  const [state, setState] = useState<SkillEditorState | null>(null);
  const [refresh, setRefresh] = useState(0);
  const [editing, setEditing] = useState(false);
  const [buffers, setBuffers] = useState<Record<string, string>>({});
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const live = useRef(true);
  const submitting = useRef(false);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController(); setState(null);
    api.post<SkillEditorState>(manualUrl("editor"), { skill_id: skillId, revision_id: revision }, { signal: controller.signal }).then(({ data }) => {
      if (controller.signal.aborted) return;
      if (data.skill_id !== skillId || data.selected_revision !== revision || !data.head_commit || !data.head_revision || !data.latest_revision) throw Error();
      setState(data);
    }).catch(() => { if (!controller.signal.aborted) setError("skill_manual_controls_unavailable"); });
    return () => controller.abort();
  }, [skillId, revision, refresh]);
  const changes = useMemo(() => (snapshot?.files || []).filter((file) => file.kind === "text" &&
    Object.prototype.hasOwnProperty.call(buffers, file.path) && buffers[file.path] !== file.text)
    .map((file) => ({ path: file.path, content: buffers[file.path] })), [snapshot, buffers]);
  const files = useMemo(() => (snapshot?.files || []).map((file) => editing && Object.prototype.hasOwnProperty.call(buffers, file.path) ?
    { ...file, text: buffers[file.path], bytes: new TextEncoder().encode(buffers[file.path]).length } : file), [snapshot, buffers, editing]);
  useEffect(() => {
    if (!changes.length && !pending) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [changes.length, pending]);
  const discard = () => { if (!busy && !pending) { setEditing(false); setBuffers({}); setMessage(""); } };
  const submit = async (request: Pending) => {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true); setPending(request); setError(""); setStatus("");
    try {
      const { data } = await api.post(manualUrl(request.action), request.body);
      if (!live.current) return;
      if (request.action === "save") {
        const saved = data as SaveResult;
        if (saved.skill?.skill_id !== skillId || saved.skill.tree_hash !== saved.skill.revision_id || !saved.commit?.commit_id) throw Error();
        setEditing(false); setBuffers({}); setMessage(""); onSaved(saved.skill.revision_id);
        setStatus("Commit saved. Registry current is unchanged.");
      } else {
        if (data.skill_id !== skillId || data.revision_id !== request.body.revision_id || data.commit_id !== request.body.commit_id || data.promotion_performed !== true) throw Error();
        setStatus("Published to the Skill registry. Existing graphs keep their pinned revisions.");
      }
      setPending(null); setRefresh((value) => value + 1);
    } catch (failure) {
      if (!live.current) return;
      const code = (failure as { response?: { data?: { detail?: { code?: string } } } }).response?.data?.detail?.code;
      const definitive = typeof code === "string" && /^skill_manual_(not_authorized|stale|invalid|request_conflict|policy_denied|nothing_to_publish|save_expired)$/.test(code);
      setError(definitive ? code! : "skill_manual_unavailable");
      if (definitive) { setPending(null); setRefresh((value) => value + 1); }
    } finally { submitting.current = false; if (live.current) setBusy(false); }
  };
  return { state, files, editing, changes, message, setMessage, busy, pending, error, status,
    dismissError: () => setError(""), refresh: () => { setError(""); setRefresh((value) => value + 1); },
    start: () => { if (state?.can_edit && !busy && !pending) { setEditing(true); setStatus(""); } }, discard,
    update: (path: string, text: string) => setBuffers((old) => ({ ...old, [path]: text })),
    save: () => { if (state?.can_edit && changes.length && message.trim() && !pending) void submit({ action: "save", body: {
      request_id: uuid(), skill_id: skillId, revision_id: revision, commit_id: state.head_commit,
      operation: { action: "modify", message: message.trim(), files: changes },
    } }); },
    publish: (expectedLatest: string) => { if (state?.can_publish && !pending) void submit({ action: "publish", body: {
      skill_id: skillId, revision_id: revision, commit_id: state.head_commit, expected_latest: expectedLatest,
    } }); },
    reconcile: () => { if (pending) void submit(pending); },
  };
}

export type SkillEditing = ReturnType<typeof useSkillEditing>;
