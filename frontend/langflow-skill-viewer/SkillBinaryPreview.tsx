import { useMemo, useState } from "react";
import { toByteArray, fromByteArray } from "base64-js";
import type { WorkingFile } from "./SkillWorkingTree";

/** Only decoded, bounded inert image bytes enter an img; all other formats stay hex. */
export default function SkillBinaryPreview({ file }: { file: WorkingFile }) {
  const [failed, setFailed] = useState(false);
  const content = useMemo(() => {
    try {
      const encoded = file.contentBase64 ?? file.binary_base64 ?? file.image_data_url?.split(",")[1];
      if (!encoded || encoded.length > 699052) return null;
      const bytes = toByteArray(encoded);
      if (bytes.length > 512 * 1024 || bytes.length !== file.bytes) return null;
      const starts = (...values: number[]) => values.every((value, index) => bytes[index] === value);
      const mime = starts(137, 80, 78, 71, 13, 10, 26, 10) ? "image/png" : starts(255, 216, 255) ? "image/jpeg" :
        starts(71, 73, 70, 56, 55, 97) || starts(71, 73, 70, 56, 57, 97) ? "image/gif" :
        starts(82, 73, 70, 70) && bytes[8] === 87 && bytes[9] === 69 && bytes[10] === 66 && bytes[11] === 80 ? "image/webp" :
        starts(0, 0, 1, 0) ? "image/x-icon" : null;
      return { bytes, url: mime ? `data:${mime};base64,${fromByteArray(bytes)}` : null };
    } catch { return null; }
  }, [file]);
  const [limit, setLimit] = useState(4096);
  return <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-auto p-4" aria-label={`Binary preview: ${file.path}`}>
    <p className="mb-3 break-all text-xs text-muted-foreground">{file.bytes} bytes · {file.file_hash}</p>
    {content?.url && !failed ? <img src={content.url} alt={`Preview of ${file.path}`} className="min-h-0 max-w-full self-center object-contain" onError={() => setFailed(true)} /> :
      content ? <>
        {failed && <p role="status" className="mb-2 text-sm">The image could not be decoded. Showing its bytes.</p>}
        <pre tabIndex={0} aria-label={`Hex bytes: ${file.path}`} className="overflow-auto text-xs leading-5">{Array.from({ length: Math.ceil(Math.min(limit, content.bytes.length) / 16) }, (_, row) => {
          const offset = row * 16, values = [...content.bytes.subarray(offset, offset + 16)];
          return `${offset.toString(16).padStart(8, "0")}  ${values.map((byte) => byte.toString(16).padStart(2, "0")).join(" ").padEnd(47)}  ${values.map((byte) => byte >= 32 && byte < 127 ? String.fromCharCode(byte) : ".").join("")}`;
        }).join("\n")}</pre>
        {limit < content.bytes.length && <button type="button" className="mt-2 self-start rounded border px-2 py-1 text-sm" onClick={() => setLimit((value) => value + 4096)}>Show more bytes</button>}
      </> : <p className="text-sm">Preview bytes are unavailable for this file.</p>}
  </div>;
}
