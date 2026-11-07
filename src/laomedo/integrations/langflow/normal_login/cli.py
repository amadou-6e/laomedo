"""CLI composition for explicit bootstrap verification."""

import argparse
from laomedo.integrations.langflow.normal_login.settings import NormalLoginSettings
from laomedo.integrations.langflow.normal_login.startup import NormalLoginStartup


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "username", help="Explicit non-secret bootstrap administrator name"
    )
    arguments = parser.parse_args()
    from langflow.services.deps import get_settings_service
    from lfx.services.settings.constants import (
        DEFAULT_SUPERUSER,
        LEGACY_DEFAULT_SUPERUSER_PASSWORD,
    )

    startup = NormalLoginStartup(NormalLoginSettings().runtime_root)
    startup.confirm_bootstrap(
        arguments.username,
        get_settings_service().auth_settings,
        DEFAULT_SUPERUSER,
        LEGACY_DEFAULT_SUPERUSER_PASSWORD.get_secret_value(),
    )
    print("Administrator bootstrap verified; no password was retained.")
