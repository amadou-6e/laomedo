"""Own the lifecycle of one loopback HTTP server for internal controls."""

from threading import Thread


class RunningHTTPServer:
    """Start and fully release only the server supplied by the caller."""

    def __init__(self, server):
        """Retain the caller's unstarted server without opening other resources."""
        self.server = server
        self.thread = Thread(
            target=lambda: server.serve_forever(poll_interval=0.05), daemon=True
        )

    def __enter__(self):
        """Start the owned thread and return the supplied server for requests."""
        self.thread.start()
        return self.server

    def __exit__(self, *_):
        """Close the socket and join the owned thread, or report incomplete cleanup."""
        try:
            if self.thread.ident is not None:
                self.server.shutdown()
        finally:
            self.server.server_close()
            if self.thread.ident is not None:
                self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise RuntimeError("Owned HTTP server thread did not stop")
