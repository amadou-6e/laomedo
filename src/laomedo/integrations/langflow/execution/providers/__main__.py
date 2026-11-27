"""Container-only entry point for an isolated saved-provider graph."""

import asyncio

from laomedo.integrations.langflow.execution.providers.native import (
    NativeProviderGraphWorker,
)


def main():
    return asyncio.run(NativeProviderGraphWorker().run())


if __name__ == "__main__":
    raise SystemExit(main())
