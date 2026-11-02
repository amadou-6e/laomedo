import { useEffect, useState, type ReactNode } from "react";

export function useSkillNavigation(identity: string, paths: string[]) {
  const [open, setOpen] = useState({ Files: true, Commits: true });
  const [collapsedFolders, setCollapsedFolders] = useState<Set<string>>(new Set());
  const folders = [...new Set(paths.flatMap((path) => {
    const parts = path.split("/");
    return parts.slice(0, -1).map((_, index) => parts.slice(0, index + 1).join("/"));
  }))];
  useEffect(() => { setOpen({ Files: true, Commits: true }); setCollapsedFolders(new Set()); }, [identity]);
  const allOpen = open.Files && open.Commits && folders.every((path) => !collapsedFolders.has(path));
  return {
    open, collapsedFolders, allOpen,
    toggleSection: (name: keyof typeof open) => setOpen((current) => ({ ...current, [name]: !current[name] })),
    toggleFolder: (path: string) => setCollapsedFolders((current) => {
      const next = new Set(current); if (next.has(path)) next.delete(path); else next.add(path); return next;
    }),
    toggleAll: () => { setOpen({ Files: !allOpen, Commits: !allOpen }); setCollapsedFolders(new Set(allOpen ? folders : [])); },
  };
}

export default function SkillNavigation({ files, commits, open, onToggle }: {
  files: ReactNode; commits: ReactNode; open: { Files: boolean; Commits: boolean };
  onToggle: (name: "Files" | "Commits") => void;
}) {
  return <div role="group" className="flex min-h-0 flex-1 flex-col" aria-label="Skill navigation sections">
    {([['Files', files], ['Commits', commits]] as const).map(([name, body]) => <section key={name}
      className={`relative flex min-h-0 flex-col border-b ${open[name] ? 'flex-1' : 'shrink-0'}`}>
      <div className="flex h-8 shrink-0 items-center bg-muted/50">
        <button type="button" aria-expanded={open[name]} aria-controls={`skill-${name}-body`}
          className="flex min-w-0 flex-1 items-center gap-1 px-1 py-1 text-left text-xs font-semibold uppercase tracking-wide focus-visible:outline focus-visible:-outline-offset-2"
          onClick={() => onToggle(name)}>
          <span aria-hidden="true">{open[name] ? '\u25be' : '\u25b8'}</span>{name}
        </button>
      </div>
      <div id={`skill-${name}-body`} hidden={!open[name]} style={{ display: open[name] ? 'flex' : 'none' }}
        className="min-h-0 flex-1 flex-col overflow-auto">{body}</div>
    </section>)}
  </div>;
}
