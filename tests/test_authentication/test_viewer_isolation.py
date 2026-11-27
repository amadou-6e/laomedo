"""The native graph app must never start with the GitHub vault in its process."""

from importlib.util import find_spec
import unittest
from unittest.mock import patch

if find_spec("langflow") is None:
    raise unittest.SkipTest("The optional native Langflow app is not installed")

from laomedo.integrations.langflow.authentication.errors import PrivateSessionError
from laomedo.integrations.langflow.viewer import create_app


class ViewerIsolationTests(unittest.TestCase):
    """Private connection admission must stop before native app construction."""

    def test_private_connections_refused_before_constructing_native_app(self):
        with patch("langflow.main.create_app") as upstream:
            for value in (True, "False"):
                with self.subTest(value=value):
                    with self.assertRaises(PrivateSessionError):
                        create_app(profile_runtime=object(), private_connections=value)
            upstream.assert_not_called()
