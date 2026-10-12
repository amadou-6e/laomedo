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
    target.mkdir()
    shutil.copy2(overlay / "SkillFilesModal.tsx", target / "index.tsx")
    shutil.copy2(overlay / "MONACO-LICENSE.txt", checkout / "src/frontend/public/monaco-LICENSE.txt")
    print("pinned_skill_viewer_overlay_applied")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    apply(parser.parse_args().checkout)
