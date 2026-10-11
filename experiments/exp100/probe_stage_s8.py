"""Fresh one-shot S8 identity for the reviewed binary-stream stage candidate.

The S7 probe core supplies the same evidence/fixture machinery; its consumed
identity and committed failed observation are never reused or overwritten.
"""

from pathlib import Path
import sys

from . import probe_stage_s7 as core


core.IDENTITY = "exp100-s8-20261009-a"
core.EVIDENCE = Path(__file__).resolve().parent / "observation-s8.json"
core.PENDING = Path(__file__).resolve().parent / "observation-s8.json.pending"
core.DRIVER_PATH = Path(__file__)
core.POSITIVE_SUFFIX = "s8-positive"
core.NEGATIVE_SUFFIX = "s8-wrong-commit"


if __name__ == "__main__":
    sys.exit(core.main())
