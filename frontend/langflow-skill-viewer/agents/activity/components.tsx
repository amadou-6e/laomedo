import { useId, useRef, useState, type ReactNode } from "react";
import { Search } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { statusPresentation } from "./utils";
import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import IconComponent from "@/components/common/genericIconComponent";
import SimplifiedCodeTabComponent from "@/components/core/codeTabsComponent";
import { Button } from "@/components/ui/button";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";

// Keep standard scrollbar properties at auto so Chromium uses the button-free styling.
export const ACTIVITY_SCROLLBAR_CLASS =
  "[scrollbar-width:auto] [scrollbar-color:auto] [scrollbar-gutter:stable] dark:[color-scheme:dark] [&::-webkit-scrollbar]:h-2 [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-muted-foreground/60 [&::-webkit-scrollbar-thumb:hover]:bg-muted-foreground/80 [&::-webkit-scrollbar-button]:hidden [&::-webkit-scrollbar-button]:h-0 [&::-webkit-scrollbar-button]:w-0 [&::-webkit-scrollbar-corner]:bg-transparent";

export function HighlightedJson({ value }: { value: unknown }) {
  return (
    <SimplifiedCodeTabComponent
      code={JSON.stringify(value, null, 2) ?? "null"}
      language="json"
    />
  );
}

// The upstream code font rule is !important; override it locally for transcript code.
export function MessageMarkdown({
  text,
  allowLinks = true,
}: {
  text: string;
  allowLinks?: boolean;
}) {
  return (
    <Markdown
      remarkPlugins={[remarkGfm]}
      skipHtml
      disallowedElements={allowLinks ? ["img"] : ["img", "a"]}
      unwrapDisallowed={!allowLinks}
      className="prose prose-sm max-w-none break-words dark:prose-invert prose-code:before:content-none prose-code:after:content-none prose-code:!font-mono prose-code:font-normal [&_pre]:overflow-x-auto [&_pre]:whitespace-pre-wrap [&_code]:break-words"
      components={{
        table: ({ node, ...props }) => (
          <div className="max-w-full overflow-x-auto">
            <table {...props} />
          </div>
        ),
        code: ({ node, ...props }) => (
          <code
            {...props}
            style={{
              fontFamily:
                "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
              fontWeight: 400,
            }}
          />
        ),
        a: ({ node, ...props }) => (
          <a {...props} target="_blank" rel="noopener noreferrer" />
        ),
      }}
    >
      {text}
    </Markdown>
  );
}

export function SectionHeading({
  children,
  id,
  actions,
}: {
  children: React.ReactNode;
  id?: string;
  actions?: React.ReactNode;
}) {
  return (
    <div className="flex min-w-0 items-center gap-5">
      <h2
        id={id}
        className="shrink-0 text-xs font-semibold uppercase tracking-wide text-muted-foreground"
      >
        {children}
      </h2>
      <div className="h-px min-w-4 flex-1 bg-border" />
      {actions && (
        <div className="flex shrink-0 items-center gap-2">{actions}</div>
      )}
    </div>
  );
}

export function ActivityInfo({ label, text }: { label: string; text: string }) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-6 w-6 text-muted-foreground"
          aria-label={label}
        >
          <IconComponent name="Info" className="h-3.5 w-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent className="max-w-[calc(100vw-2rem)] text-xs" align="end">
        {text}
      </PopoverContent>
    </Popover>
  );
}

export function JsonDisclosure({
  label,
  value,
  className,
}: {
  label: string;
  value: unknown;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  return (
    <details
      className={className}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className="cursor-pointer text-xs text-muted-foreground">
        {label}
      </summary>
      {open && (
        <div className="mt-2 min-w-0">
          <HighlightedJson value={value} />
        </div>
      )}
    </details>
  );
}

export function MessageSource({ value }: { value: unknown }) {
  const [open, setOpen] = useState(false);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon"
          className="h-5 w-5 shrink-0 text-muted-foreground"
          title="View message source"
          aria-label="View message source"
        >
          <IconComponent name="Code" className="h-3.5 w-3.5" />
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="end"
        collisionPadding={12}
        aria-label="Message source"
        className={`${ACTIVITY_SCROLLBAR_CLASS} max-h-[70vh] w-[min(520px,calc(100vw-2rem))] overflow-auto p-3`}
        onKeyDown={(event) => event.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-3">
          <h3 className="text-sm font-medium">Message source</h3>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6"
            aria-label="Close message source"
            onClick={() => setOpen(false)}
          >
            <IconComponent name="X" className="h-3.5 w-3.5" />
          </Button>
        </div>
        {open && <HighlightedJson value={value} />}
      </PopoverContent>
    </Popover>
  );
}

/** Shared bubble appearance; the caller owns speaker metadata and plain-text/Markdown semantics. */
export function UserMessageBubble({
  children,
  constrainWidth = true,
}: {
  children: ReactNode;
  constrainWidth?: boolean;
}) {
  return (
    <div
      className={`rounded-xl rounded-tr-sm border bg-muted/50 px-4 py-3 text-sm leading-[1.7142857] ${constrainWidth ? "max-w-[90%] md:max-w-[80%]" : ""}`}
    >
      {children}
    </div>
  );
}

/** Own the section search lifecycle so hidden filters and keyboard focus cannot drift. */
export function useSectionSearch({
  label,
  query,
  onQueryChange,
  placeholder,
}: {
  label: string;
  query: string;
  onQueryChange: (value: string) => void;
  placeholder: string;
}) {
  const [open, setOpen] = useState(false);
  const inputId = useId();
  const buttonRef = useRef<HTMLButtonElement>(null);
  const close = () => {
    onQueryChange("");
    setOpen(false);
    buttonRef.current?.focus();
  };
  const button = (
    <Button
      type="button"
      ref={buttonRef}
      variant="ghost"
      size="sm"
      className="h-7 w-7 p-0"
      aria-label={open ? `Close ${label} search` : `Search ${label}`}
      aria-expanded={open}
      aria-controls={open ? inputId : undefined}
      title={open ? "Close search" : "Search"}
      onClick={() => (open ? close() : setOpen(true))}
    >
      <Search aria-hidden="true" className="h-3.5 w-3.5" />
    </Button>
  );
  const field = open && (
    <div className="flex min-w-0 items-center gap-3">
      <div className="relative min-w-0 flex-1">
        <Search
          aria-hidden="true"
          className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-muted-foreground"
        />
        <input
          autoFocus
          id={inputId}
          value={query}
          onChange={(event) => onQueryChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Escape") {
              event.preventDefault();
              close();
            }
          }}
          aria-label={`Search ${label}`}
          placeholder={placeholder}
          className="h-9 w-full rounded-md border bg-background pl-9 pr-16 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        />
        {query && (
          <button
            type="button"
            onClick={() => onQueryChange("")}
            className="absolute right-3 top-2 text-xs text-muted-foreground underline"
          >
            Clear
          </button>
        )}
      </div>
    </div>
  );
  return { button, field };
}

/** Keep status text and badge semantics shared across the timeline and selected detail. */
export function StatusBadge({ status }: { status: string }) {
  const { label, tone } = statusPresentation(status);
  const variant =
    tone === "success"
      ? "successStatic"
      : tone === "active" || status === "waiting"
        ? "secondaryStatic"
        : "errorStatic";
  return (
    <Badge size="tag" variant={variant}>
      {label}
    </Badge>
  );
}

export function StatusDot({ status }: { status: string }) {
  const { label, tone } = statusPresentation(status);
  const color =
    tone === "success" || tone === "active"
      ? "bg-accent-emerald-foreground"
      : tone === "pending"
        ? "bg-muted-foreground/60"
        : "bg-error-foreground";
  return (
    <span
      aria-hidden="true"
      title={label}
      className={`h-1.5 w-1.5 shrink-0 rounded-full ${color}`}
    />
  );
}
