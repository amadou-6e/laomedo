"""Apply the small viewer overlay to the exact upstream Langflow revision."""
from pathlib import Path
import argparse
import shutil
import subprocess

UPSTREAM = "fec71dca901949c09ed4d63315804337cd2eb13d"
ROOT = Path(__file__).resolve().parents[1]

def apply(checkout):
    checkout = checkout.resolve()
    revision = subprocess.check_output(["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True).strip()
    if revision != UPSTREAM:
        raise SystemExit("pinned_langflow_checkout_required")
    overlay = ROOT / "frontend/langflow-skill-viewer"
    patch = overlay / "upstream.patch"
    target = checkout / "src/frontend/src/modals/skillFilesModal"
    if target.exists() or subprocess.check_output(["git", "-C", str(checkout), "status", "--porcelain"]).strip():
        raise SystemExit("clean_upstream_checkout_required")
    subprocess.run(["git", "-C", str(checkout), "apply", "--check", str(patch)], check=True)
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)
    agent_target = checkout / "src/frontend/src/CustomNodes/GenericNode/components/RenderInputParameters"
    shutil.copy2(overlay / "RenderAgentInputParameters.tsx", agent_target / "index.tsx")
    shutil.copy2(overlay / "AgentAdvancedControls.tsx", agent_target / "AgentAdvancedControls.tsx")
    shutil.copy2(overlay / "AgentAdvancedControls.test.tsx", agent_target / "AgentAdvancedControls.test.tsx")
    target.mkdir()
    shutil.copy2(overlay / "SkillFilesModal.tsx", target / "index.tsx")
    shutil.copy2(overlay / "SkillActions.tsx", target / "SkillActions.tsx")
    shutil.copy2(overlay / "SkillActions.test.tsx", target / "SkillActions.test.tsx")
    shutil.copy2(overlay / "SkillNavigation.tsx", target / "SkillNavigation.tsx")
    shutil.copy2(overlay / "SkillNavigation.test.tsx", target / "SkillNavigation.test.tsx")
    shutil.copy2(overlay / "SkillOverview.tsx", target / "SkillOverview.tsx")
    shutil.copy2(overlay / "SkillOverview.test.tsx", target / "SkillOverview.test.tsx")
    shutil.copy2(overlay / "SkillFileDiff.tsx", target / "SkillFileDiff.tsx")
    shutil.copy2(overlay / "SkillFileDiff.test.tsx", target / "SkillFileDiff.test.tsx")
    shutil.copy2(overlay / "SkillHistory.tsx", target / "SkillHistory.tsx")
    shutil.copy2(overlay / "SkillHistory.test.tsx", target / "SkillHistory.test.tsx")
    shutil.copy2(overlay / "SkillSplitPane.tsx", target / "SkillSplitPane.tsx")
    shutil.copy2(overlay / "SkillSplitPane.test.tsx", target / "SkillSplitPane.test.tsx")
    shutil.copy2(overlay / "selection.ts", target / "selection.ts")
    shutil.copy2(overlay / "MONACO-LICENSE.txt", checkout / "src/frontend/public/monaco-LICENSE.txt")
    issue_target = checkout / "src/frontend/src/modals/issueViewerModal"
    issue_target.mkdir()
    shutil.copy2(overlay / "IssueViewerModal.tsx", issue_target / "index.tsx")
    pr_target = checkout / "src/frontend/src/modals/prViewerModal"
    pr_target.mkdir()
    shutil.copy2(overlay / "PRViewerModal.tsx", pr_target / "index.tsx")
    activity_target = checkout / "src/frontend/src/modals/agentActivity"
    activity_target.mkdir()
    shutil.copy2(overlay / "AgentActivity.tsx", activity_target / "index.tsx")
    agents_patch = overlay / "agents.patch"
    # HEAD stays pinned; patch context tolerates whitespace differences, including Windows CRLF.
    subprocess.run(["git", "-C", str(checkout), "apply", "--ignore-space-change", "--check", str(agents_patch)], check=True)
    subprocess.run(["git", "-C", str(checkout), "apply", "--ignore-space-change", str(agents_patch)], check=True)
    agents_target = checkout / "src/frontend/src/modals/graphAgents"
    agents_target.mkdir()
    shutil.copy2(overlay / "AgentActivityNavigation.ts", checkout / "src/frontend/src/stores/agentActivityStore.ts")
    shutil.copy2(overlay / "GraphAgents.tsx", agents_target / "index.tsx")
    shutil.copy2(overlay / "GraphAgents.test.tsx", agents_target / "index.test.tsx")
    recovery_target = checkout / "src/frontend/src/components/laomedoRecovery"
    recovery_target.mkdir()
    for name in ("RunnerRecovery.tsx", "RunnerRecovery.test.tsx"):
        shutil.copy2(overlay / name, recovery_target / name)
    flow_path = checkout / "src/frontend/src/pages/FlowPage/components/flowBuildingComponent/index.tsx"
    flow = flow_path.read_text(encoding="utf-8")
    flow = 'import RunnerRecovery, { isRunnerConnectionError } from "@/components/laomedoRecovery/RunnerRecovery";\n' + flow
    replacements = [
        ('  const errorButtonsRef = useRef<HTMLDivElement>(null);', '  const runnerRecoveryError = Boolean(buildInfo?.error?.some(isRunnerConnectionError));\n  const errorButtonsRef = useRef<HTMLDivElement>(null);'),
        ('                                  <Button size="sm" onClick={handleRetry}>', '                                  {!runnerRecoveryError && <Button size="sm" onClick={handleRetry}>'),
        ('{t("flowBuild.retry")}\n                                  </Button>', '{t("flowBuild.retry")}\n                                  </Button>}'),
        ('className="absolute right-0 font-mono text-xs"', 'className={cn("absolute right-0 font-mono text-xs", runnerRecoveryError && "hidden")}'),
        ('className="max-h-48 overflow-y-auto"', 'className="max-h-[60vh] overflow-y-auto"'),
        ('                        <Markdown\n', '                        {runnerRecoveryError ? <RunnerRecovery message={buildInfo?.error?.find(isRunnerConnectionError)} /> : <Markdown\n'),
        ('                        </Markdown>', '                        </Markdown>}'),
    ]
    for before, after in replacements:
        if flow.count(before) != 1:
            raise SystemExit("pinned_runner_recovery_anchor_missing: " + before[:80])
        flow = flow.replace(before, after)
    flow_path.write_text(flow, encoding="utf-8")
    print("pinned_skill_viewer_overlay_applied")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    apply(parser.parse_args().checkout)
