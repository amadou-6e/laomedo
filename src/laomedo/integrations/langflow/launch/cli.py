"""Launch the local app without hand-written environment-variable bootstraps."""

import argparse
from pathlib import Path

from pydantic import ValidationError

from laomedo.integrations.langflow.launch.service import AppLauncher
from laomedo.integrations.langflow.launch.settings import Settings


def main() -> None:
    """Parse trusted host paths and run the app; report invalid setup before binding."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-config", type=Path, required=True)
    parser.add_argument("--frontend", type=Path, required=True)
    parser.add_argument("--components", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args()
    try:
        AppLauncher(Settings(**vars(args))).run()
    except ValidationError:
        parser.exit(2, "Invalid app arguments. Check the paths and loopback port.\n")
    except ValueError as exc:
        parser.exit(2, str(exc) + "\n")


if __name__ == "__main__":
    main()
