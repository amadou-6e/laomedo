import { useState, type ReactNode } from "react";

export default function SkillNavigation({ files, commits }: { files: ReactNode; commits: ReactNode }) {
  const [open, setOpen] = useState({ Files: true, Commits: true });
  return <div className="flex min-h-0 flex-1 flex-col" aria-label="Skill navigation sections">
    {([['Files', files], ['Commits', commits]] as const).map(([name, body]) => <section key={name}
      className={`relative flex min-h-0 flex-col border-b ${open[name] ? 'flex-1' : 'shrink-0'}`}>
      <div className="flex h-8 shrink-0 items-center bg-muted/50">
        <button type="button" aria-expanded={open[name]} aria-controls={`skill-${name}-body`}
          className="flex min-w-0 flex-1 items-center gap-1 px-1 py-1 text-left text-xs font-semibold uppercase tracking-wide focus-visible:outline focus-visible:-outline-offset-2"
          onClick={() => setOpen({ ...open, [name]: !open[name] })}>
          <span aria-hidden="true">{open[name] ? '\u25be' : '\u25b8'}</span>{name}
        </button>
        <details className="relative mr-1">
          <summary aria-label={`${name} actions`} className="flex h-6 w-7 cursor-pointer list-none items-center justify-center rounded text-lg leading-none hover:bg-muted [&::-webkit-details-marker]:hidden">{'\u22ef'}</summary>
          <div className="absolute right-0 top-7 z-20 w-44 rounded border bg-background p-1 shadow-md"
            onClick={(event) => { event.currentTarget.parentElement?.removeAttribute('open'); }}>
            <button type="button" className="w-full px-2 py-1 text-left text-sm hover:bg-muted"
              onClick={() => setOpen({ Files: name === 'Files', Commits: name === 'Commits' })}>Expand only {name.toLowerCase()}</button>
            <button type="button" className="w-full px-2 py-1 text-left text-sm hover:bg-muted"
              onClick={() => setOpen({ Files: true, Commits: true })}>Expand both sections</button>
          </div>
        </details>
      </div>
      <div id={`skill-${name}-body`} hidden={!open[name]} style={{ display: open[name] ? 'flex' : 'none' }}
        className="min-h-0 flex-1 flex-col overflow-auto">{body}</div>
    </section>)}
  </div>;
}
