import IconComponent from "@/components/common/genericIconComponent";
import openAiLogo from "./assets/openai-logo.svg";
import openCodeLogoDark from "./assets/opencode-logo-dark.svg";
import openCodeLogoLight from "./assets/opencode-logo-light.svg";

/** Use the same provider brand assets in welcome cards and account choices. */
export default function ProviderIcon({ provider, className = "h-4 w-4" }: {
  provider: string; className?: string;
}) {
  return <span aria-hidden="true" className={`inline-flex shrink-0 items-center justify-center ${className}`}>
    {provider === "codex" ? <img src={openAiLogo} className="h-full w-full object-contain invert dark:invert-0" alt="" />
      : provider === "claude" ? <IconComponent name="Claude" className="h-full w-full" />
      : <><img src={openCodeLogoLight} className="h-full w-full object-contain dark:hidden" alt="" /><img src={openCodeLogoDark} className="hidden h-full w-full object-contain dark:block" alt="" /></>}
  </span>;
}
