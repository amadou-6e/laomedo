import IconComponent from "@/components/common/genericIconComponent";
import openAiLogo from "./assets/openai-logo.svg";
import openCodeLogoDark from "./assets/opencode-logo-dark.svg";
import openCodeLogoLight from "./assets/opencode-logo-light.svg";
import claudeMark from "./assets/claude-mark.svg";

/** Use the same provider brand assets in welcome cards and account choices. */
export default function ProviderIcon({ provider, className = "h-4 w-4", monochrome = false }: {
  provider: string; className?: string; monochrome?: boolean;
}) {
  return <span aria-hidden="true" className={`inline-flex shrink-0 items-center justify-center ${className}`}>
    {provider === "codex" ? <img src={openAiLogo} className="h-full w-full object-contain invert dark:invert-0" alt="" />
      : provider === "claude" ? monochrome ? <img src={claudeMark} className="h-full w-full object-contain invert dark:invert-0" alt="" /> : <IconComponent name="Claude" className="h-full w-full" />
      : monochrome ? <svg viewBox="0 0 240 300" fill="currentColor" className="h-full w-full"><path d="M180 60H60V240H180V60ZM240 300H0V0H240V300Z" /></svg>
      : <><img src={openCodeLogoLight} className="h-full w-full object-contain dark:hidden" alt="" /><img src={openCodeLogoDark} className="hidden h-full w-full object-contain dark:block" alt="" /></>}
  </span>;
}
