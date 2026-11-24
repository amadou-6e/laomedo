"""Thread ownership for Codex sessions that must survive between requests."""

import asyncio
import threading

from laomedo.agents.errors import RunnerError


class CodexSessionOwner:
    """Keep native transports on one running event loop until explicit teardown.

    The Agent closes its exact native resources before closing this owner. This
    object never reconstructs a transport, submits a prompt or selects an account.
    """

    def __init__(self):
        """Start a dedicated daemon thread and wait until its event loop is ready."""
        self._ready = threading.Event()
        self._guard = threading.Lock()
        self._closed = False
        self._loop = None
        self._thread = threading.Thread(
            target=self._serve, name="laomedo-codex-session", daemon=True
        )
        self._thread.start()
        self._ready.wait()

    def run(self, operation):
        """Execute an admitted coroutine on the original native transport thread."""
        with self._guard:
            if self._closed:
                operation.close()
                raise RunnerError("runner_transport_failed")
            future = asyncio.run_coroutine_threadsafe(operation, self._loop)
        return future.result()

    def close(self):
        """Stop after resource cleanup, cancel remaining readers and join the thread."""
        with self._guard:
            if self._closed:
                return
            self._closed = True
            self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join()

    def _serve(self):
        """Create, run and close the event loop only on its owning thread."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        self._ready.set()
        try:
            loop.run_forever()
        finally:
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            loop.run_until_complete(loop.shutdown_asyncgens())
            loop.run_until_complete(loop.shutdown_default_executor())
            loop.close()
