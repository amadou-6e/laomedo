"""Load only the isolated experiment harness; do not shadow the installed wheel."""
from pathlib import Path
import sys

_harness_path = str(Path(__file__).resolve().parents[1] / "experiments")
sys.path.insert(0, _harness_path)
try:
    from turn_harness import VerificationLocalRunner, VerificationOpenCodeRunner
finally:
    sys.path.remove(_harness_path)
