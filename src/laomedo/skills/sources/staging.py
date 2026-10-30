"""Own clone staging lifetime, retaining it when process cleanup is unconfirmed."""

from tempfile import TemporaryDirectory


class SkillSourceStagingDirectory(TemporaryDirectory):
    """Normal stdlib cleanup, with explicit preservation for an uncertain child."""

    def __init__(self, *, dir, prefix="clone-"):
        self._preserved = False
        super().__init__(dir=dir, prefix=prefix)

    def preserve(self) -> None:
        """Detach the stdlib finalizer before leaving an uncertain clone operation.

        Python 3.10 has no public TemporaryDirectory retention option. Keep this
        single lifecycle dependency here and exercise it in the supported matrix.
        """
        self._preserved = True
        self._finalizer.detach()

    def cleanup(self) -> None:
        """Retain uncertain staging; preserve stdlib permission handling otherwise."""
        if not self._preserved:
            super().cleanup()
