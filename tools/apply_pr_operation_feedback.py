"""Apply PR Operation feedback UI support after the pinned viewer overlay."""

import argparse
from pathlib import Path
import subprocess


def apply(checkout):
    checkout = checkout.resolve()
    if (
        subprocess.check_output(
            ["git", "-C", str(checkout), "rev-parse", "HEAD"], text=True
        ).strip()
        != "fec71dca901949c09ed4d63315804337cd2eb13d"
    ):
        raise SystemExit("pinned_langflow_checkout_required")
    patch = (
        Path(__file__).resolve().parents[1]
        / "frontend/langflow-skill-viewer/pr-operation-feedback.patch"
    )
    subprocess.run(
        ["git", "-C", str(checkout), "apply", "--check", str(patch)], check=True
    )
    subprocess.run(["git", "-C", str(checkout), "apply", str(patch)], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("checkout", type=Path)
    apply(parser.parse_args().checkout)
