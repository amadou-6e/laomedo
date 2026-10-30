"""Internal recording seam; never use this interceptor as integration evidence."""
import subprocess
from laomedo.git.command import GitCommandRunner
from laomedo.git.settings import MEDIATED_TOKEN_ENV


class CallbackGitRunner(GitCommandRunner):
    """Reuse production argument/environment projection while controlling effects."""

    def __init__(self, callback):
        self.callback = callback

    def _execute(self, command, home):
        environment = self.environment(command, home)
        try:
            return self.callback(self._arguments(command, home), capture_output=True,
                                 check=False, timeout=command.context.timeout, env=environment)
        finally:
            environment.pop(MEDIATED_TOKEN_ENV, None)


class InspectingGitRunner(GitCommandRunner):
    """Observe or fault a typed command before delegating to the real runner."""

    def __init__(self, callback):
        self.callback = callback

    def run(self, command):
        override = self.callback(command)
        return override if isinstance(override, subprocess.CompletedProcess) else super().run(command)
