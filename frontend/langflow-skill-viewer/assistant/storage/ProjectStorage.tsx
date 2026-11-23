import { useEffect, useRef, useState } from "react";
import { FolderGit2 } from "lucide-react";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { AssistantFailure, assistantRequest } from "../api";
import type { ProjectStorageState } from "./models";

export default function ProjectStorage({ onFailure }: { onFailure: (error: unknown) => void }) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<ProjectStorageState>();
  const [name, setName] = useState("");
  const [path, setPath] = useState("");
  const [agentRepo, setAgentRepo] = useState("");
  const [agentPath, setAgentPath] = useState("agent-files");
  const [graph, setGraph] = useState("");
  const [graphRepo, setGraphRepo] = useState("");
  const [graphPath, setGraphPath] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const generation = useRef(0);
  const controller = useRef<AbortController>();

  useEffect(() => () => { generation.current++; controller.current?.abort(); }, []);

  async function refresh(signal?: AbortSignal) {
    const result = await assistantRequest<ProjectStorageState>("/storage", undefined, signal);
    setState(result);
    return result;
  }

  function failed(failure: unknown) {
    const code = failure instanceof AssistantFailure ? failure.code : "assistant_storage_unavailable";
    if (code === "assistant_session_locked") onFailure(failure);
    const messages: Record<string, string> = {
      assistant_storage_repository_unavailable: "The checkout is unavailable. Use an existing local Git checkout.",
      assistant_storage_path_invalid: "Choose a normal relative project path without links, private folders or environment files.",
      assistant_storage_file_changed: "The file changed or already exists. Refresh storage and inspect it before saving again.",
      assistant_source_revision_changed: "The saved graph changed. Refresh storage before trying again.",
      assistant_storage_graph_locked: "Unlock the graph in the editor before loading its file.",
      assistant_storage_location_conflict: "Graph files and agent files need separate locations. Another graph may already use this file.",
      assistant_storage_graph_invalid: "This file or graph is not supported by the portable graph format. The saved graph was preserved.",
      assistant_storage_file_missing: "The selected graph file is missing. Save it first or restore the checkout.",
      assistant_storage_file_too_large: "The selected file exceeds the pilot file limit.",
    };
    setError(messages[code] ?? "Storage could not be confirmed. Refresh before trying again; your existing app graph remains available.");
  }

  async function perform(operation: () => Promise<string>) {
    if (busy) return;
    const token = ++generation.current;
    setBusy(true); setNotice(""); setError("");
    controller.current = new AbortController();
    try {
      const message = await operation();
      if (token !== generation.current) return;
      await refresh(controller.current.signal);
      if (token === generation.current) setNotice(message);
    } catch (failure) {
      if (token === generation.current) failed(failure);
    } finally {
      if (token === generation.current) setBusy(false);
    }
  }

  function chooseGraph(id: string) {
    setGraph(id);
    const binding = state?.graphs[id];
    setGraphRepo(binding?.location.repository_id ?? state?.repositories[0]?.id ?? "");
    setGraphPath(binding?.location.path ?? `graphs/${id}.json`);
  }

  const input = "w-full rounded-md border bg-background px-3 py-2 text-sm";
  const button = "rounded-md border px-3 py-1.5 text-sm hover:bg-muted disabled:opacity-40";
  const choices = <><option value="">Select repository</option>{state?.repositories.map(repo => <option key={repo.id} value={repo.id}>{repo.name}</option>)}</>;
  const selectedGraph = state?.workflows.find(row => row.id === graph);
  const binding = state?.graphs[graph];
  const sameLocation = binding?.location.repository_id === graphRepo && binding?.location.path === graphPath;

  async function synchronize(operation: "save" | "load") {
    if (!selectedGraph) return;
    await perform(async () => {
      const result = await assistantRequest<{ diagnostics: string[] }>(`/storage/graphs/${graph}/${operation}`, {
        location: { repository_id: graphRepo, path: graphPath },
        expected_graph_revision: selectedGraph.revision,
        expected_file_hash: sameLocation ? binding?.current_sha256 : null,
      }, controller.current?.signal);
      return (operation === "save" ? "Graph file saved." : "Graph file loaded. Reload open graph editors before editing again.") + (result.diagnostics.length ? " App-managed or incomplete settings remain in Laomedo; inspect the graph in the editor." : "");
    });
  }

  return <Dialog open={open} onOpenChange={value => {
    if (busy) return;
    setOpen(value); setError(""); setNotice("");
    if (value) void perform(async () => {
      const result = await refresh();
      setAgentRepo(result.agent_files?.repository_id ?? result.repositories[0]?.id ?? "");
      setAgentPath(result.agent_files?.path ?? "agent-files");
      return "";
    });
  }}>
    <DialogTrigger asChild><button type="button" aria-label="Project storage" title="Project storage" className="rounded p-1.5 hover:bg-muted"><FolderGit2 size={16} /></button></DialogTrigger>
    <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-xl">
      <DialogHeader><DialogTitle>Project storage</DialogTitle><DialogDescription>Local Git checkouts. Graph files save and load explicitly; editor autosave stays in Laomedo. No automatic commits or pushes.</DialogDescription></DialogHeader>
      <fieldset disabled={busy} className="min-w-0 space-y-5 disabled:opacity-60">
        <section className="space-y-2">
          <h3 className="text-sm font-medium">Connect a checkout</h3>
          <label className="block text-xs">Repository name<input className={input} value={name} onChange={event => setName(event.target.value)} /></label>
          <label className="block text-xs">Local checkout path<input className={input} value={path} placeholder="C:\projects\my-project" onChange={event => setPath(event.target.value)} /></label>
          <button className={button} type="button" disabled={!name.trim() || !path.trim()} onClick={() => void perform(async () => {
            await assistantRequest("/storage/repositories", {name: name.trim(), path: path.trim()}, controller.current?.signal);
            setName(""); setPath(""); return "Checkout connected.";
          })}>Connect checkout</button>
        </section>
        <section className="space-y-2 border-t pt-4">
          <h3 className="text-sm font-medium">Agent files</h3>
          <p className="text-xs text-muted-foreground">Persistent files available to chat through Laomedo tools.</p>
          {state?.agent_files && <p className="break-all text-xs text-muted-foreground">Current: {state.repositories.find(repo => repo.id === state.agent_files?.repository_id)?.name} / {state.agent_files.path}</p>}
          <label className="block text-xs">Agent repository<select className={input} value={agentRepo} onChange={event => setAgentRepo(event.target.value)}>{choices}</select></label>
          <label className="block text-xs">Agent folder<input className={input} value={agentPath} onChange={event => setAgentPath(event.target.value)} /></label>
          <button className={button} type="button" disabled={!agentRepo || !agentPath} onClick={() => void perform(async () => {
            await assistantRequest("/storage/agent-files", {repository_id: agentRepo, path: agentPath}, controller.current?.signal);
            return "Agent-files folder selected. Chat can access it through project file tools.";
          })}>Use folder</button>
        </section>
        <section className="space-y-2 border-t pt-4">
          <h3 className="text-sm font-medium">Graph files</h3>
          {sameLocation && binding?.sha256 !== binding?.current_sha256 && <p className="text-xs text-muted-foreground">The file changed since its last synchronization. Load to use the file, or save to replace it with the app graph.</p>}
          <label className="block text-xs">Graph<select className={input} value={graph} onChange={event => chooseGraph(event.target.value)}><option value="">Select graph</option>{state?.workflows.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>
          <label className="block text-xs">Graph repository<select className={input} value={graphRepo} onChange={event => setGraphRepo(event.target.value)}>{choices}</select></label>
          <label className="block text-xs">Graph JSON file<input className={input} value={graphPath} onChange={event => setGraphPath(event.target.value)} /></label>
          <div className="flex gap-2"><button className={button} type="button" disabled={!selectedGraph || !graphRepo || !graphPath} onClick={() => void synchronize("save")}>Save graph file</button><button className={button} type="button" disabled={!selectedGraph || !sameLocation} onClick={() => {
            if (window.confirm("Replace this saved graph with its file contents? Reload open graph editors afterward.")) void synchronize("load");
          }}>Load graph file</button></div>
          <p className="text-xs text-muted-foreground">Portable files omit secrets and component code. Loading preserves existing app-managed settings on matching components.</p>
        </section>
        <button className={button} type="button" onClick={() => void perform(async () => "Storage refreshed.")}>Refresh storage</button>
      </fieldset>
      {busy && <p role="status" className="text-sm text-muted-foreground">Working…</p>}
      {notice && <p role="status" className="text-sm text-muted-foreground">{notice}</p>}
      {error && <p role="alert" className="text-sm text-destructive">{error}</p>}
    </DialogContent>
  </Dialog>;
}
