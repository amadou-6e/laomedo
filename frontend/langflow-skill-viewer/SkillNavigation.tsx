import { SkillChevron } from "./SkillIcons";
import { useEffect, useState, type ReactNode } from "react";

export function useSkillNavigation(identity: string, paths: string[], directories: string[] = []) {
  const [open, setOpen] = useState({ Find: false, Files: true, Commits: true });
  const [collapsedFolders, setCollapsedFolders] = useState<Set<string>>(new Set());
  const fileFolders = [...new Set([...directories, ...paths.flatMap((path) => {
    const parts = path.split("/");
    return parts.slice(0, -1).map((_, index) => parts.slice(0, index + 1).join("/"));
  })])];
  const folders = [...fileFolders, ...fileFolders.map((path) => `search:folder:${path}`), ...paths.map((path) => `search:file:${path}`)];
  useEffect(() => { setOpen({ Find: false, Files: true, Commits: true }); setCollapsedFolders(new Set()); }, [identity]);
  const allOpen = open.Find && open.Files && open.Commits && folders.every((path) => !collapsedFolders.has(path));
  return {
    open, collapsedFolders, allOpen,
    showFind: () => setOpen((current) => ({ ...current, Find: true })),
    hideFind: () => setOpen((current) => ({ ...current, Find: false })),
    toggleSection: (name: keyof typeof open) => setOpen((current) => ({ ...current, [name]: !current[name] })),
    toggleFolder: (path: string) => setCollapsedFolders((current) => {
      const next = new Set(current); if (next.has(path)) next.delete(path); else next.add(path); return next;
    }),
    toggleAll: () => { setOpen({ Find: !allOpen, Files: !allOpen, Commits: !allOpen }); setCollapsedFolders(new Set(allOpen ? folders : [])); },
  };
}

export default function SkillNavigation({ files, commits, find, open, onToggle }: {
  files: ReactNode; commits: ReactNode; find?: ReactNode; open: { Find?: boolean; Files: boolean; Commits: boolean };
  onToggle: (name: "Find" | "Files" | "Commits") => void;
}) {
  return <div role="group" className="flex min-h-0 flex-1 flex-col" aria-label="Skill navigation sections">
    {([...(find ? [['Find', find] as const] : []), ['Files', files], ['Commits', commits]] as const).map(([name, body]) => <section key={name}
      className={`relative flex min-h-0 flex-col border-b ${open[name] ? 'flex-1' : 'shrink-0'}`}>
      <div className="flex h-8 shrink-0 items-center bg-muted/50">
        <button id={`skill-${name}-toggle`} type="button" aria-expanded={open[name]} aria-controls={`skill-${name}-body`}
          className="flex min-w-0 flex-1 items-center gap-1 px-1 py-1 text-left text-xs font-semibold uppercase tracking-wide focus-visible:outline focus-visible:-outline-offset-2"
          onClick={() => onToggle(name)}>
          <SkillChevron expanded={!!open[name]} />{name}
        </button>
      </div>
      <div id={`skill-${name}-body`} hidden={!open[name]} style={{ display: open[name] ? 'flex' : 'none' }}
        className="min-h-0 flex-1 flex-col overflow-auto">{body}</div>
    </section>)}
  </div>;
}
