import { useState } from "react";
import PopupFrame, { popupButtonStyle } from "@/components/laomedoRecovery/PopupFrame";
// Preserve native application guidance, without adding Agent lifecycle assumptions.
export function nativeErrorText(value: unknown): string {
  if (Array.isArray(value)) return value.filter(item => typeof item === "string").map(nativeErrorText).join("\n");
  if (typeof value !== "string") return "";
  const text = value.slice(0, 8192);
  if (/^\s*[\[{]/.test(text)) return "Technical payload omitted.";
  return text.split("\n").filter(line => !/^\s*(at\s+\S|Traceback|File\s+\")/.test(line)).join("\n")
    .replace(/\b(Bearer\s+)\S+/gi, "$1[redacted]")
    .replace(/\b(password|api[_-]?key|access[_-]?token|secret)\s*[:=]\s*[^\s,;]+/gi, "$1=[redacted]");
}
export default function ApplicationErrorPopup({ title, list = [], onDismiss, autoFocus = false }: {
  title: string; list?: unknown[]; onDismiss: () => void; autoFocus?: boolean;
}) {
  const [copied, setCopied] = useState("");
  const heading = nativeErrorText(title), messages = list.map(nativeErrorText).filter(Boolean);
  const copy = async () => {
    try { await navigator.clipboard.writeText([heading, ...messages].join("\n\n")); setCopied("Copied"); }
    catch { setCopied("Copy unavailable. Select the error text to copy it manually."); }
  };
  return <PopupFrame label="Application error" autoFocus={autoFocus} onClose={onDismiss}
    heading={<h3 className="select-text text-sm font-bold">{heading}</h3>}
    footer={<><button type="button" style={popupButtonStyle} onClick={() => void copy()}>Copy error</button><button type="button" style={popupButtonStyle} onClick={onDismiss}>Dismiss</button></>}>
    <div className="select-text">{messages.map((message, index) => <p key={index} className={index ? "mt-2 whitespace-pre-wrap break-words" : "whitespace-pre-wrap break-words"}>{message}</p>)}</div>
    {copied && <p role="status" className="mt-2">{copied}</p>}
  </PopupFrame>;
}
