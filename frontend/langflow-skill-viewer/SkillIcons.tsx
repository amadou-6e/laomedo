import type { IconType } from "react-icons";
import { SiCss, SiDocker, SiGnubash, SiGo, SiHtml5, SiJavascript, SiJson, SiPython, SiRust, SiToml, SiTypescript, SiYaml } from "react-icons/si";
import { VscChevronDown, VscChevronRight, VscFile, VscFileBinary, VscFileMedia } from "react-icons/vsc";

type FileAppearance = { Icon: IconType; label: string; color: string };
// Exact E060 outline from VS Code's bundled Seti font (1000 units/em).
// View box preserves Seti's 150% file-icon scale. See skill-icons-NOTICE.txt.
const SetiMarkdown: IconType = ({ size = 16, ...props }) => <svg width={size} height={size} viewBox="167 167 666 666" fill="currentColor" {...props}>
  <path transform="translate(0 1000) scale(1 -1)" d="M647 791V481H766Q675 388 494 206L231 478H341V794L353 785Q408 747 436 729Q486 697 496.5 697.0Q507 697 545 722Q568 736 615 769Z" />
</svg>;
const appearances: Record<string, FileAppearance> = {
  markdown: { Icon: SetiMarkdown, label: "Markdown", color: "text-[#498ba7] dark:text-[#519aba]" },
  python: { Icon: SiPython, label: "Python", color: "text-blue-500 dark:text-blue-300" },
  javascript: { Icon: SiJavascript, label: "JavaScript", color: "text-yellow-700 dark:text-yellow-300" },
  typescript: { Icon: SiTypescript, label: "TypeScript", color: "text-blue-600 dark:text-blue-300" },
  json: { Icon: SiJson, label: "JSON", color: "text-yellow-700 dark:text-yellow-300" },
  yaml: { Icon: SiYaml, label: "YAML", color: "text-red-600 dark:text-red-300" },
  toml: { Icon: SiToml, label: "TOML", color: "text-red-700 dark:text-red-300" },
  shell: { Icon: SiGnubash, label: "Shell", color: "text-green-700 dark:text-green-300" },
  html: { Icon: SiHtml5, label: "HTML", color: "text-orange-700 dark:text-orange-300" },
  css: { Icon: SiCss, label: "CSS", color: "text-purple-600 dark:text-purple-300" },
  rust: { Icon: SiRust, label: "Rust", color: "text-orange-800 dark:text-orange-300" },
  go: { Icon: SiGo, label: "Go", color: "text-cyan-700 dark:text-cyan-300" },
  docker: { Icon: SiDocker, label: "Docker", color: "text-blue-600 dark:text-blue-300" },
  image: { Icon: VscFileMedia, label: "Image", color: "text-purple-600 dark:text-purple-300" },
  binary: { Icon: VscFileBinary, label: "Binary", color: "text-muted-foreground" },
  file: { Icon: VscFile, label: "File", color: "text-muted-foreground" },
};
const extensions: Record<string, string> = {
  md: "markdown", markdown: "markdown", mdx: "markdown", py: "python", pyi: "python",
  js: "javascript", jsx: "javascript", mjs: "javascript", cjs: "javascript",
  ts: "typescript", tsx: "typescript", mts: "typescript", cts: "typescript",
  json: "json", jsonc: "json", jsonl: "json", yaml: "yaml", yml: "yaml", toml: "toml",
  sh: "shell", bash: "shell", zsh: "shell", html: "html", htm: "html", css: "css",
  rs: "rust", go: "go", png: "image", jpg: "image", jpeg: "image", gif: "image",
  webp: "image", svg: "image", ico: "image", bin: "binary",
};

export function SkillFileIcon({ path }: { path: string }) {
  const name = path.split("/").pop()?.toLowerCase() || "";
  const extension = name.includes(".") ? name.split(".").pop() || "" : "";
  const extensionType = Object.prototype.hasOwnProperty.call(extensions, extension) ? extensions[extension] : "file";
  const type = /^dockerfile(?:\.|$)/.test(name) ? "docker" : extensionType;
  const { Icon, color, label } = appearances[type];
  return <span aria-hidden="true" data-file-type={type} title={`${label} file`} className={`inline-flex h-4 w-4 shrink-0 items-center justify-center ${color}`}>
    <Icon size={16} focusable="false" />
  </span>;
}

export function SkillChevron({ expanded }: { expanded: boolean }) {
  const Icon = expanded ? VscChevronDown : VscChevronRight;
  return <Icon aria-hidden="true" focusable="false" data-chevron={expanded ? "down" : "right"} className="h-4 w-4 shrink-0 text-muted-foreground" />;
}
