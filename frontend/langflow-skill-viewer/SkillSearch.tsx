import { useDeferredValue, useMemo, useState } from "react";
import type { SkillFile } from "./SkillHistory";

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

export default function SkillSearch({ files, onSelect }: { files: SkillFile[]; onSelect: (match: SkillMatch) => void }) {
  const [query, setQuery] = useState("");
  const [matchCase, setMatchCase] = useState(false);
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
      {[...groups].map(([path, matches]) => <details key={path} open className="text-sm">
        <summary className="cursor-pointer break-all bg-muted/40 px-2 py-1">{path} <span className="text-xs">({matches.length})</span></summary>
        {matches.map((match) => {
          const start = Math.max(0, match.column - 1 - 35), end = Math.min(match.text.length, match.column - 1 + match.length + 65);
          return <button key={match.line} type="button" aria-label={`${path}, line ${match.line}`}
            className="block w-full truncate px-3 py-1 text-left font-mono text-xs hover:bg-muted focus-visible:bg-muted"
            title={`${match.line}: ${match.text}`} onClick={() => onSelect(match)}>
            <span className="mr-2 opacity-60">{match.line}:</span>{start > 0 ? "…" : ""}{match.text.slice(start, match.column - 1)}
            <mark className="bg-yellow-200 text-black dark:bg-yellow-700 dark:text-white">{match.text.slice(match.column - 1, match.column - 1 + match.length)}</mark>
            {match.text.slice(match.column - 1 + match.length, end)}{end < match.text.length ? "…" : ""}
          </button>;
        })}
      </details>)}
    </div>
  </div>;
}
