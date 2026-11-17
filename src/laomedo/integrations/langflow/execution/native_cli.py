"""Container-only native graph API entry point, without broker identity state."""

import argparse
from pathlib import Path
from uuid import UUID

import uvicorn

from laomedo.integrations.langflow.execution.native import NativeProfileRuntime
from laomedo.integrations.langflow.execution.settings import (
    NativeProfileSettings,
    NATIVE_PROFILE_PORT,
)


def main():
    """Bind only container loopback; the supervisor supplies the exact owner/store."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner-id", type=UUID, required=True)
    parser.add_argument("--state-root", type=Path, required=True)
    arguments = parser.parse_args()
    runtime = NativeProfileRuntime(
        NativeProfileSettings(
            owner_id=arguments.owner_id,
            state_root=arguments.state_root,
        )
    )
    uvicorn.run(
        runtime.create_app(),
        host="127.0.0.1",
        port=NATIVE_PROFILE_PORT,
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
