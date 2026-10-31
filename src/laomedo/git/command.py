"""The single bounded host Git process implementation."""

from contextlib import contextmanager
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory

from .errors import GitCommandTimeout
from .models import GitCommand, GitEnvironmentProfile
from .settings import GIT_TREE_CLEANUP_SECONDS, MEDIATED_TOKEN_ENV


class GitCommandRunner:
    """Execute admitted Git commands; authorization stays with the calling feature."""

    @contextmanager
    def isolated_home(
        self,
        profile: GitEnvironmentProfile,
        *,
        prefix="laomedo-git-home-",
        ignore_cleanup_errors=None,
    ):
        """Own a sequence home, preserving each existing profile's cleanup behavior."""
        ignore = (
            profile == GitEnvironmentProfile.HOST_TRANSPORT
            if ignore_cleanup_errors is None
            else ignore_cleanup_errors
        )
        with TemporaryDirectory(prefix=prefix, ignore_cleanup_errors=ignore) as home:
            yield Path(home)

    def run(self, command: GitCommand) -> subprocess.CompletedProcess:
        """Execute once under its exact profile; return bytes or a cleanup-aware timeout.

        OSError from startup propagates to the caller's existing error mapping.
        The private credential environment is cleared on every exit path.
        """
        if command.context.home is not None:
            return self._execute(command, command.context.home)
        with self.isolated_home(
            command.context.profile,
            ignore_cleanup_errors=command.context.ignore_home_cleanup_errors,
        ) as home:
            return self._execute(command, home)

    def environment(self, command: GitCommand, home: Path) -> dict[str, str]:
        """Build the existing private profile at point of use, without global mutation."""
        environment = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith(("GIT_", "GCM_"))
            and key
            not in {"GH", "GH_TOKEN", "GITHUB_TOKEN", "SSH_ASKPASS", MEDIATED_TOKEN_ENV}
        }
        environment.update(
            HOME=str(home),
            USERPROFILE=str(home),
            XDG_CONFIG_HOME=str(home),
            GIT_CONFIG_GLOBAL=os.devnull,
            GIT_CONFIG_SYSTEM=os.devnull,
            GIT_CONFIG_NOSYSTEM="1",
            GIT_TERMINAL_PROMPT="0",
            GIT_NO_REPLACE_OBJECTS="1",
        )
        if command.context.profile == GitEnvironmentProfile.WORKSPACE:
            environment.update(GIT_OPTIONAL_LOCKS="0", GIT_LFS_SKIP_SMUDGE="1")
        else:
            environment["GIT_ASKPASS"] = ""
        environment.pop("HOMEDRIVE", None)
        environment.pop("HOMEPATH", None)
        environment.update(command.context.extra_env)
        if command.credential is not None:
            environment[MEDIATED_TOKEN_ENV] = (
                command.credential.token.get_secret_value()
            )
        return environment

    def _arguments(self, command: GitCommand, home: Path) -> list[str]:
        """Project the native invocation without ever placing a token in argv."""
        arguments = ["git"]
        configuration = list(command.configuration)
        if command.context.hardened:
            configuration = [
                ("core.fsmonitor", "false"),
                ("core.hooksPath", str(home)),
                *configuration,
            ]
        if command.credential is not None:
            helper = Path(__file__).with_name("credentials") / "helper.py"
            invocation = (
                "!" + shlex.quote(sys.executable) + " " + shlex.quote(str(helper))
            )
            configuration.extend(
                [("credential.helper", ""), ("credential.helper", invocation)]
            )
        for key, value in configuration:
            arguments.extend(["-c", key + "=" + value])
        if command.directory is not None:
            arguments.extend(["-C", str(command.directory)])
        arguments.extend(command.arguments)
        return arguments

    def _execute(self, command: GitCommand, home: Path) -> subprocess.CompletedProcess:
        """Bind native arguments and isolate their full process tree under a deadline."""
        environment = self.environment(command, home)
        arguments = self._arguments(command, home)
        options = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "env": environment,
        }
        if command.context.profile == GitEnvironmentProfile.WORKSPACE:
            options["stdin"] = subprocess.DEVNULL
        if os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        try:
            process = subprocess.Popen(arguments, **options)
            try:
                stdout, stderr = process.communicate(timeout=command.context.timeout)
            except subprocess.TimeoutExpired:
                cleanup = self._stop_tree(process)
                raise GitCommandTimeout(
                    arguments, command.context.timeout, cleanup
                ) from None
            return subprocess.CompletedProcess(
                arguments, process.returncode, stdout, stderr
            )
        finally:
            environment.pop(MEDIATED_TOKEN_ENV, None)

    def _stop_tree(self, process) -> bool:
        """Preserve the fuller existing bounded cleanup, including inherited pipes."""
        cleanup_verified = False
        if os.name == "nt":
            try:
                killed = subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=GIT_TREE_CLEANUP_SECONDS,
                )
                cleanup_verified = killed.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                pass
        else:
            try:
                os.killpg(process.pid, signal.SIGKILL)
                cleanup_verified = True
            except OSError:
                pass
        if process.poll() is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
        try:
            process.communicate(timeout=GIT_TREE_CLEANUP_SECONDS)
        except subprocess.TimeoutExpired:
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
            try:
                process.wait(timeout=GIT_TREE_CLEANUP_SECONDS)
            except subprocess.TimeoutExpired:
                cleanup_verified = False
        return cleanup_verified
