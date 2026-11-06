import { useDeferredValue, useMemo, useState } from "react";
import type { SkillFile } from "../models";
import { SkillChevron, SkillFileIcon } from "../explorer/SkillIcons";

export type SkillMatch = { path: string; line: number; column: number; length: number; text: string };

// Literal matching only: user input never becomes an executable regular expression.
export function searchSkill(files: SkillFile[], query: string, matchCase: boolean) {
  const matches: SkillMatch[] = [];
  if (!query) return { matches, truncated: false };
  const expression = new RegExp(query.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), matchCase ? "" : "i");
  for (const file of files) {
    if (file.kind !== "text" || file.text == null) continue;
    const lines = file.text.split(/\r\n|\n|\r/);
    for (let index = 0; index < lines.length; index++) {
      const match = expression.exec(lines[index]);
      if (!match) continue;
      if (matches.length === 500) return { matches, truncated: true };
      matches.push({ path: file.path, line: index + 1, column: match.index + 1, length: match[0].length, text: lines[index] });
    }
  }
  return { matches, truncated: false };
}

type SearchNode = { path: string; name: string; children: Map<string, SearchNode>; matches: SkillMatch[]; count: number };

function matchTree(matches: SkillMatch[]) {
  const root: SearchNode = { path: "", name: "", children: new Map(), matches: [], count: matches.length };
  for (const match of matches) {
    let node = root;
    for (const name of match.path.split("/")) {
      const path = node.path ? `${node.path}/${name}` : name;
      if (!node.children.has(name)) node.children.set(name, { name, path, children: new Map(), matches: [], count: 0 });
      node = node.children.get(name)!; node.count++;
    }
    node.matches.push(match);
  }
  return root;
}

function SearchBranch({ node, collapsed, onToggle, onSelect }: { node: SearchNode; collapsed: Set<string>;
  onToggle: (path: string) => void; onSelect: (match: SkillMatch) => void }) {
  return <ul className={node.path ? "ml-4 border-l" : ""}>
    {[...node.children.values()].map((child) => {
      const file = child.matches.length > 0, key = `search:${file ? "file" : "folder"}:${child.path}`, expanded = !collapsed.has(key);
      return <li key={child.path}>
        <button type="button" title={child.path} aria-label={`${file ? "Search file" : "Search folder"}: ${child.path}`}
          aria-expanded={expanded} onClick={() => onToggle(key)}
          className="flex h-7 w-full min-w-0 items-center gap-1 px-1 text-left text-sm hover:bg-muted">
          <SkillChevron expanded={expanded} />{file && <SkillFileIcon path={child.path} />}
          <span className="min-w-0 flex-1 truncate">{child.name}</span><span className="pr-1 text-xs text-muted-foreground">{child.count}</span>
        </button>
        <div hidden={!expanded}>
          {file ? <ul className="ml-4 border-l">{child.matches.map((match) => {
            const start = Math.max(0, match.column - 1 - 35), end = Math.min(match.text.length, match.column - 1 + match.length + 65);
            return <li key={match.line}><button type="button" aria-label={`${match.path}, line ${match.line}`}
              className="block w-full truncate px-2 py-1 text-left font-mono text-xs hover:bg-muted focus-visible:bg-muted"
              title={`${match.line}: ${match.text}`} onClick={() => onSelect(match)}>
              <span className="mr-2 opacity-60">{match.line}:</span>{start > 0 ? "…" : ""}{match.text.slice(start, match.column - 1)}
              <mark className="bg-yellow-200 text-black dark:bg-yellow-700 dark:text-white">{match.text.slice(match.column - 1, match.column - 1 + match.length)}</mark>
              {match.text.slice(match.column - 1 + match.length, end)}{end < match.text.length ? "…" : ""}
            </button></li>;
          })}</ul> : <SearchBranch node={child} collapsed={collapsed} onToggle={onToggle} onSelect={onSelect} />}
        </div>
      </li>;
    })}
  </ul>;
}

export default function SkillSearch({ files, onSelect, collapsed: supplied, onToggle }: { files: SkillFile[]; onSelect: (match: SkillMatch) => void;
  collapsed?: Set<string>; onToggle?: (path: string) => void }) {
  const [query, setQuery] = useState("");
  const [matchCase, setMatchCase] = useState(false);
  const [localCollapsed, setLocalCollapsed] = useState(new Set<string>());
  const collapsed = supplied || localCollapsed;
  const toggle = onToggle || ((path: string) => setLocalCollapsed((current) => { const next = new Set(current); if (next.has(path)) next.delete(path); else next.add(path); return next; }));
  const deferred = useDeferredValue(query);
  const result = useMemo(() => searchSkill(files, deferred, matchCase), [files, deferred, matchCase]);
  const groups = new Map<string, SkillMatch[]>();
  for (const match of result.matches) groups.set(match.path, [...(groups.get(match.path) || []), match]);
  return <div className="flex min-h-0 flex-1 flex-col" aria-label="Search pinned current Skill files">
    <div className="flex shrink-0 gap-1 p-2">
      <input type="search" aria-label="Search all Skill files" placeholder="Search all text files…"
        className="min-w-0 flex-1 rounded border bg-background px-2 py-1 text-sm" value={query}
        onChange={(event) => setQuery(event.target.value)} />
      <button type="button" aria-label="Match case" aria-pressed={matchCase} title="Match case"
        className={`rounded border px-2 text-sm ${matchCase ? "bg-muted" : ""}`} onClick={() => setMatchCase(!matchCase)}>Aa</button>
    </div>
    <p role="status" className="shrink-0 px-2 pb-1 text-xs">
      {query !== deferred ? "Searching…" : !query ? "Search pinned current text files." : !result.matches.length ?
        "No matches in pinned current files." : result.truncated ? "First 500 matching lines shown. Refine search." :
        `${result.matches.length} matching ${result.matches.length === 1 ? "line" : "lines"} in ${groups.size} ${groups.size === 1 ? "file" : "files"}.`}
    </p>
    <div className="min-h-0 flex-1 overflow-auto" aria-label="Skill search results" aria-busy={query !== deferred}>
      <SearchBranch node={matchTree(result.matches)} collapsed={collapsed} onToggle={toggle} onSelect={onSelect} />
    </div>
  </div>;
}
