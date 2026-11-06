import type { SkillFile } from "../models";
import { SkillChevron, SkillFileIcon } from "./SkillIcons";
import type { ReactElement, ReactNode } from "react";

type Branch = { name: string; path: string; children?: Branch[] };
export type ExplorerEntry = { path: string; folder: boolean };
type ExplorerState = { active: string; collapsed: Set<string>; select: (path: string) => void; onToggle: (path: string) => void;
  decorate?: (entry: ExplorerEntry, row: ReactElement) => ReactNode };

function tree(files: SkillFile[], folders: string[]): Branch[] {
  const roots: Branch[] = [];
  for (const file of [...folders.map((path) => ({ path: path + "/" })), ...files]) {
    let level = roots;
    const parts = file.path.split("/").filter(Boolean);
    parts.forEach((name, index) => {
      let item = level.find((entry) => entry.name === name);
      if (!item) {
        item = { name, path: parts.slice(0, index + 1).join("/") };
        if (index < parts.length - 1 || file.path.endsWith("/")) item.children = [];
        level.push(item);
      }
      if (item.children) level = item.children;
    });
  }
  return roots;
}

function Folder({ item, ...state }: ExplorerState & { item: Branch }) {
  const expanded = !state.collapsed.has(item.path);
  const row = <button type="button" title={item.path} className="flex h-7 w-full min-w-0 items-center gap-1 rounded border-0 px-1 text-left text-sm outline-none ring-0 hover:bg-muted focus-visible:bg-[#005fb8] focus-visible:text-white focus-visible:outline-none focus-visible:ring-0 dark:focus-visible:bg-[#4aa0ff] dark:focus-visible:text-black"
      aria-expanded={item.children ? expanded : undefined}
      aria-current={!item.children && state.active === item.path ? "true" : undefined}
      onClick={() => item.children ? state.onToggle(item.path) : state.select(item.path)}>
      {item.children ? <SkillChevron expanded={expanded} /> : <>
        <span aria-hidden="true" className="h-4 w-4 shrink-0" />
        <SkillFileIcon path={item.path} />
      </>}
      <span className="min-w-0 truncate">{item.name}{item.children?.length === 0 && <span className="ml-2 text-xs text-muted-foreground">(empty · not saved)</span>}</span>
    </button>;
  return <li className="min-w-0">
    {state.decorate ? state.decorate({ path: item.path, folder: !!item.children }, row) : row}
    {item.children && <ul hidden={!expanded} style={{ display: expanded ? undefined : "none" }} className="ml-4 min-w-0 border-l">
      {item.children.map((child) => <Folder key={child.path} item={child} {...state} />)}
    </ul>}
  </li>;
}

export default function SkillExplorer({ files, folders = [], ...state }: ExplorerState & { files: SkillFile[]; folders?: string[] }) {
  return <ul className="min-w-0">{tree(files, folders).map((item) => <Folder key={item.path} item={item} {...state} />)}</ul>;
}
