"""Checkout-only bridge; installed code and resources live in src/laomedo."""
from pathlib import Path as _Path
_source = _Path(__file__).resolve().parent.parent.joinpath("src", "laomedo")
if not _source.is_dir():
    raise ImportError("Laomedo source package is missing; restore src/laomedo or install the package.")
__path__ = [str(_source)]
