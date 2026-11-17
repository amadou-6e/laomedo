"""Private pipe entry point for a fresh single-job native graph process."""

import asyncio

from laomedo.integrations.langflow.execution.worker import NativeGraphWorker

if __name__ == "__main__":
    raise SystemExit(asyncio.run(NativeGraphWorker().run()))
