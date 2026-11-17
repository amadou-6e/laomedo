"""Persistent assistant and pure workflow-authoring contract controls."""

from importlib.util import find_spec
from unittest import SkipTest

if find_spec("langflow") is None:
    raise SkipTest(
        "Assistant integration controls require the optional pinned Langflow runtime"
    )
