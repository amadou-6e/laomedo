import { useEffect, useMemo, useRef, useState } from "react";
import { v4 as uuid } from "uuid";
import { api } from "@/controllers/API/api";
import { getBaseUrl } from "@/customization/utils/urls";
import type { Snapshot } from "./SkillHistory";
import { fileActionErrors, fileEdits, folderPaths, replayTreeChange, validateEditSize, validateTree, workingFiles, type FileBuffers, type WorkingFile, type WorkingTree, type TreeChange } from "./SkillWorkingTree";

export type SkillEditorState = { skill_id: string; selected_revision: string; head_revision: string; head_commit: string;
  latest_revision: string; can_edit: boolean; can_publish: boolean; edit_enabled: boolean };
type SaveResult = { skill: { skill_id: string; revision_id: string; tree_hash: string }; commit: { commit_id: string } };
type Candidate = { revision: string; commit: string };
type Pending = { action: "save" | "publish"; body: Record<string, unknown>; expectedLatest: string };
const manualUrl = (action: string) => `${getBaseUrl()}laomedo/skills/manual/${action}`;

export function useSkillEditing(skillId: string, revision: string, snapshot: Snapshot | null, onSaved: (revision: string) => void, importing = false) {
  const [state, setState] = useState<SkillEditorState | null>(null);
  const [controlsUnavailable, setControlsUnavailable] = useState(false);
  const [refresh, setRefresh] = useState(0);
  const [buffers, setBuffers] = useState<FileBuffers>(new Map());
  const [folders, setFolders] = useState<string[]>([]);
  const undo = useRef<TreeChange[]>([]), redo = useRef<TreeChange[]>([]);
  const treeIdentity = useRef(`${skillId}:${revision}`);
  useEffect(() => {
    const identity = `${skillId}:${revision}`;
    if (treeIdentity.current !== identity) {
      undo.current = []; redo.current = []; setFolders([]); setBuffers(new Map()); treeIdentity.current = identity;
    }
  }, [skillId, revision]);
  const [candidate, setCandidate] = useState<Candidate | null>(null);
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const [error, setError] = useState("");
  const [status, setStatus] = useState("");
  const live = useRef(true);
  const submitting = useRef(false);
  useEffect(() => { live.current = true; return () => { live.current = false; }; }, []);
  useEffect(() => {
    const controller = new AbortController(); setState(null); setControlsUnavailable(false);
    api.post<SkillEditorState>(manualUrl("editor"), { skill_id: skillId, revision_id: revision }, { signal: controller.signal }).then(({ data }) => {
      if (controller.signal.aborted) return;
      if (data.skill_id !== skillId || data.selected_revision !== revision || !data.head_commit || !data.head_revision || !data.latest_revision) throw Error();
      setState(data);
    }).catch(() => { if (!controller.signal.aborted) { setControlsUnavailable(true); setError("skill_manual_controls_unavailable"); } });
    return () => controller.abort();
  }, [skillId, revision, refresh]);
  const files = useMemo(() => workingFiles(snapshot?.files || [], buffers), [snapshot, buffers]);
  const tree: WorkingTree = { files, folders: folderPaths(files, folders) };
  const stage = (next: WorkingTree) => {
    if (!snapshot || snapshot.revision_id !== revision || treeIdentity.current !== `${skillId}:${revision}` || !state?.can_edit || busy || pending || submitting.current) return false;
    try { validateTree(snapshot.files, next); }
    catch (failure) { setError(failure instanceof Error && (fileActionErrors as readonly string[]).includes(failure.message) ? failure.message : "skill_manual_file_invalid"); return false; }
    const staged: FileBuffers = new Map(next.files.map((file) => [file.path, file]));
    for (const file of snapshot.files) if (!staged.has(file.path)) staged.set(file.path, null);
    setBuffers(staged); setFolders(folderPaths(next.files, next.folders)); setStatus(""); return true;
  };
  const changes = useMemo(() => snapshot?.revision_id === revision ? fileEdits(snapshot.files, files) : [], [snapshot, revision, files]);
  const dirty = changes.length > 0 || !!candidate;
  useEffect(() => {
    // Only a clean workspace follows the head. Never rebase a working buffer.
    if (state?.edit_enabled && state.head_revision !== revision && !dirty && !busy && !pending && !importing) onSaved(state.head_revision);
  }, [state, revision, dirty, busy, pending, importing, onSaved]);
  useEffect(() => {
    if (!dirty && !pending) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, pending]);
  const discard = () => {
    if (busy || pending || importing) return;
    setBuffers(new Map()); setFolders([]); undo.current = []; redo.current = []; setCandidate(null); setMessage(""); setError(""); setStatus("");
    if (state) onSaved(state.head_revision);
    setRefresh((value) => value + 1);
  };
  const submit = async (initial: Pending) => {
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true); setError(""); setStatus("");
    let request = initial;
    try {
      while (true) {
        setPending(request);
        const { data } = await api.post(manualUrl(request.action), request.body);
        if (!live.current) return;
        if (request.action === "save") {
          const saved = data as SaveResult;
          if (saved.skill?.skill_id !== skillId || !saved.skill.revision_id || saved.skill.tree_hash !== saved.skill.revision_id || !saved.commit?.commit_id) throw Error();
          const next = { revision: saved.skill.revision_id, commit: saved.commit.commit_id };
          // Our confirmed save keeps local empty folders; externally followed
          // heads clear them and the action stacks in the identity effect.
          treeIdentity.current = `${skillId}:${next.revision}`;
          setCandidate(next); setBuffers(new Map()); undo.current = []; redo.current = []; onSaved(next.revision);
          request = { action: "publish", expectedLatest: request.expectedLatest, body: {
            skill_id: skillId, revision_id: next.revision, commit_id: next.commit, expected_latest: request.expectedLatest,
          } };
          continue;
        }
        if (data.skill_id !== skillId || data.revision_id !== request.body.revision_id || data.commit_id !== request.body.commit_id || data.promotion_performed !== true) throw Error();
        setCandidate(null); setMessage(""); setPending(null);
        setStatus("Published to the Skill registry. Existing graphs keep their pinned revisions.");
        setRefresh((value) => value + 1);
        break;
      }
    } catch (failure) {
      if (!live.current) return;
      const code = (failure as { response?: { data?: { detail?: { code?: string } } } }).response?.data?.detail?.code;
      const definitive = typeof code === "string" && /^skill_manual_(not_authorized|stale|invalid|request_conflict|policy_denied|nothing_to_publish|save_expired)$/.test(code);
      setError(definitive ? code! : "skill_manual_unavailable");
      if (definitive) { setPending(null); setRefresh((value) => value + 1); }
    } finally { submitting.current = false; if (live.current) setBusy(false); }
  };
  return { state, controlsUnavailable, files, tree, editing: !!state?.can_edit, dirty, candidate, changes, message, setMessage, busy, pending, error, status,
    dismissError: () => setError(""), refresh: () => { setError(""); setRefresh((value) => value + 1); }, discard,
    reportError: (code: string) => setError(code),
    update: (path: string, text: string) => {
      const file = files.find((entry) => entry.path === path);
      if (!file || file.kind !== "text" || !state?.can_edit || busy || pending || importing) return;
      setBuffers((old) => new Map(old).set(path, { ...file, text, bytes: new TextEncoder().encode(text).length })); setStatus("");
    },
    replaceFiles: (next: WorkingFile[], nextFolders = tree.folders, move?: TreeChange["move"]) => {
      const after = { files: next, folders: folderPaths(next, nextFolders) };
      if (!stage(after)) return false;
      undo.current = [...undo.current.slice(-49), { before: tree, after, move }]; redo.current = []; return true;
    },
    undoFiles: (backwards = true): TreeChange["move"] | false | undefined => {
      if (importing) return false;
      const from = backwards ? undo.current : redo.current, to = backwards ? redo.current : undo.current;
      const change = from.at(-1); if (!change || !stage(replayTreeChange(tree, change, backwards))) return false;
      from.pop(); to.push(change);
      return change.move && (backwards ? { source: change.move.destination, destination: change.move.source } : change.move);
    },
    publish: () => {
      if (!state?.can_publish || !state.can_edit || state.selected_revision !== revision || snapshot?.revision_id !== revision || treeIdentity.current !== `${skillId}:${revision}` || !dirty || busy || pending || importing) return;
      try { validateEditSize(changes); } catch { setError("skill_manual_file_limit"); return; }
      const expectedLatest = state.latest_revision;
      if (changes.length) void submit({ action: "save", expectedLatest, body: {
        request_id: uuid(), skill_id: skillId, revision_id: revision, commit_id: state.head_commit,
        operation: { action: "modify", message: message.trim() || "Update Skill files", files: changes },
      } });
      else if (candidate) void submit({ action: "publish", expectedLatest, body: {
        skill_id: skillId, revision_id: candidate.revision, commit_id: candidate.commit, expected_latest: expectedLatest,
      } });
    },
    reconcile: () => { if (pending) void submit(pending); },
  };
}

export type SkillEditing = ReturnType<typeof useSkillEditing>;
