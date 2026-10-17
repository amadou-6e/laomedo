import { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import DOMPurify from "dompurify";
import type { Snapshot } from "./SkillHistory";

export function skillDescription(text: string): { summary: string; body: string } {
  const normalized = text.replace(/\r\n?/g, "\n");
  const front = normalized.match(/^---\n([\s\S]*?)\n---(?:\n|$)/);
  const body = front ? normalized.slice(front[0].length).trim() : normalized.trim();
  const lines = front?.[1].split("\n") || [];
  const index = lines.findIndex((line) => /^description\s*:/.test(line));
  let description = index < 0 ? "" : lines[index].replace(/^description\s*:\s*/, "").trim();
  if (/^[>|][+-]?$/.test(description) || !description) {
    description = index < 0 ? "" : lines.slice(index + 1).filter((line, offset, all) =>
      /^\s/.test(line) && all.slice(0, offset).every((previous) => !previous.trim() || /^\s/.test(previous))).join(" ");
  } else if (description.startsWith('"')) {
    try { description = JSON.parse(description); } catch { description = description.replace(/^"|"$/g, ""); }
  } else if (description.startsWith("'")) description = description.replace(/^'|'$/g, "").replace(/''/g, "'");
  if (!description) description = body.split(/\n\s*\n/).find((part) => !/^(#|```|~~~|\s*[-*] )/.test(part)) || "No description is provided for this skill revision.";
  description = description.replace(/\s+/g, " ").trim();
  const sentence = description.match(/^.*?[.!?](?:\s|$)/)?.[0].trim() || description;
  return { summary: sentence, body };
}

export function bundlePath(document: string, target: string): string | null {
  let decoded: string;
  try { decoded = decodeURIComponent(target.split("#")[0]); } catch { return null; }
  if (!decoded || /[\\:\x00-\x1f?#]/.test(decoded) || decoded.startsWith("/")) return null;
  const parts = document.split("/").slice(0, -1);
  for (const part of decoded.split("/")) {
    if (part === "..") { if (!parts.length) return null; parts.pop(); }
    else if (part && part !== ".") parts.push(part);
  }
  return parts.join("/");
}

function BundleImage({ snapshot, document, src, alt }: { snapshot: Snapshot; document: string; src?: string; alt?: string }) {
  const file = snapshot.files.find((entry) => entry.path === bundlePath(document, src || ""));
  const image = useMemo(() => {
    if (!file) return null;
    if (file.image_data_url && /^data:image\/(png|jpeg|gif|webp);base64,[A-Za-z0-9+/]+=*$/.test(file.image_data_url)) return file.image_data_url;
    if (!file.path.toLowerCase().endsWith(".svg") || !file.text) return null;
    const safe = DOMPurify.sanitize(file.text, { USE_PROFILES: { svg: true },
      FORBID_TAGS: ["script", "style", "foreignObject", "image", "use", "a", "animate", "set", "animateTransform"],
      FORBID_ATTR: ["href", "xlink:href", "style"] });
    const parsed = new DOMParser().parseFromString(safe, "image/svg+xml");
    if (parsed.documentElement.localName !== "svg" || parsed.querySelector("parsererror")) return null;
    for (const element of Array.from(parsed.querySelectorAll("*"))) {
      for (const attribute of Array.from(element.attributes)) {
        if (attribute.name !== "xmlns" && /url\s*\(\s*[^#]|https?:|javascript:|data:/i.test(attribute.value)) element.removeAttribute(attribute.name);
      }
    }
    return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(new XMLSerializer().serializeToString(parsed))}`;
  }, [file]);
  if (!image) return <span className="text-muted-foreground">[Image unavailable: {alt || src || "unnamed"}]</span>;
  return <img src={image} alt={alt || file?.path || "Skill illustration"} loading="lazy" className="my-3 max-h-[420px] max-w-full rounded border object-contain" />;
}

export default function SkillOverview({ snapshot }: { snapshot: Snapshot }) {
  const skill = snapshot.files.find((file) => file.path === "SKILL.md");
  const description = useMemo(() => skillDescription(skill?.text || ""), [skill]);
  const root = snapshot.files.find((file) => file.path === "OVERVIEW.md" && file.kind === "text")?.path || "SKILL.md";
  const [full, setFull] = useState(false);
  const [document, setDocument] = useState(root);
  const file = snapshot.files.find((entry) => entry.path === document);
  const markdown = document === "SKILL.md" ? skillDescription(file?.text || "").body : file?.text || "";
  return <section aria-label="Skill overview" className="mb-3 shrink-0 border-y py-2">
    <button type="button" className="flex w-full items-start gap-2 text-left text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2"
      aria-label={full ? "Close full overview" : "Read full overview"} aria-expanded={full} aria-controls="skill-overview-content"
      onClick={() => { setFull(!full); setDocument(root); }}>
      <span aria-hidden="true" className="shrink-0">{full ? "\u25be" : "\u25b8"}</span>
      <span data-testid="skill-summary" className="min-w-0 break-words">{description.summary}</span>
    </button>
      {full && <article id="skill-overview-content" aria-label="Full skill overview" className="mt-3 max-h-[35vh] overflow-auto pt-1">
        <div className="mb-2 flex items-center gap-3 text-xs text-muted-foreground"><span>{document} Â· Current revision</span>
          {document !== root && <button type="button" className="underline" onClick={() => setDocument(root)}>Back to overview</button>}</div>
        <div className="prose prose-sm max-w-none break-words dark:prose-invert" data-testid="skill-full-overview">
          <ReactMarkdown skipHtml urlTransform={(url) => url} components={{
            a: ({ href, children }) => {
              const target = bundlePath(document, href || "");
              const local = snapshot.files.find((entry) => entry.path === target && entry.kind === "text" && entry.path.toLowerCase().endsWith(".md"));
              return local ? <button type="button" className="text-primary underline" onClick={() => setDocument(local.path)}>{children}</button> : <span>{children}</span>;
            },
            img: ({ src, alt }) => <BundleImage snapshot={snapshot} document={document} src={src} alt={alt} />,
          }}>{markdown || "No full description is provided for this skill revision."}</ReactMarkdown>
        </div>
      </article>}
  </section>;
}
