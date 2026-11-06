"""The single bounded host Git process implementation."""

from contextlib import contextmanager
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
from tempfile import TemporaryDirectory, TemporaryFile
import time

from .errors import GitCommandTimeout, GitCommandLimitExceeded, GitCommandCleanupError
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
        """Own a private configuration home for an explicit command sequence."""
        ignore = (
            profile == GitEnvironmentProfile.HOST_TRANSPORT
            if ignore_cleanup_errors is None
            else ignore_cleanup_errors
        )
        with TemporaryDirectory(prefix=prefix, ignore_cleanup_errors=ignore) as home:
            yield Path(home)

    def run(self, command: GitCommand) -> subprocess.CompletedProcess:
        """Execute once under its exact profile; return bytes or a cleanup-aware timeout.

        OSError from startup propagates to the caller's error mapping.
        The private credential environment is cleared on every exit path.
        """
        command.validate_execution_profile()
        if command.context.profile in {
            GitEnvironmentProfile.ISOLATED_HTTPS_READ_ONLY,
            GitEnvironmentProfile.ISOLATED_FILE_READ_ONLY,
        }:
            return self._execute(command, command.context.hooks_path)
        if command.context.home is not None:
            return self._execute(command, command.context.home)
        with self.isolated_home(
            command.context.profile,
            ignore_cleanup_errors=command.context.ignore_home_cleanup_errors,
        ) as home:
            return self._execute(command, home)

    def environment(self, command: GitCommand, home: Path) -> dict[str, str]:
        """Build the private execution profile at point of use, without global mutation."""
        if command.context.profile in {
            GitEnvironmentProfile.ISOLATED_HTTPS_READ_ONLY,
            GitEnvironmentProfile.ISOLATED_FILE_READ_ONLY,
        }:
            environment = {
                key: value
                for key, value in os.environ.items()
                if key.upper()
                in {
                    "PATH",
                    "SYSTEMROOT",
                    "WINDIR",
                    "SYSTEMDRIVE",
                    "COMSPEC",
                    "PATHEXT",
                    "TEMP",
                    "TMP",
                }
            }
            environment.update(
                GIT_CONFIG_NOSYSTEM="1",
                GIT_CONFIG_GLOBAL=os.devnull,
                GIT_TERMINAL_PROMPT="0",
                GIT_ASKPASS="",
                SSH_ASKPASS="",
            )
            return environment
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
        if command.context.profile in {
            GitEnvironmentProfile.ISOLATED_HTTPS_READ_ONLY,
            GitEnvironmentProfile.ISOLATED_FILE_READ_ONLY,
        }:
            if command.context.profile == GitEnvironmentProfile.ISOLATED_FILE_READ_ONLY:
                arguments.extend(["-c", "protocol.file.allow=always"])
            configuration = [
                ("credential.helper", ""),
                ("core.hooksPath", str(command.context.hooks_path)),
                ("http.followRedirects", "false"),
                ("protocol.allow", "never"),
                ("protocol.https.allow", "always"),
            ]
            for key, value in configuration:
                arguments.extend(["-c", key + "=" + value])
            arguments.extend(command.arguments)
            return arguments
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
        try:
            if command.budget is not None:
                return self._execute_budgeted(command, arguments, environment)
            process = self._start_process(
                command, arguments, environment, subprocess.PIPE, subprocess.PIPE
            )
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

    def _start_process(
        self, command, arguments, environment, stdout, stderr, *, tree=None
    ):
        """Launch one native process with its profile's cwd and stdin policy."""
        options = {"stdout": stdout, "stderr": stderr, "env": environment}
        if (
            command.context.profile == GitEnvironmentProfile.WORKSPACE
            or command.budget is not None
        ):
            options["stdin"] = subprocess.DEVNULL
        if command.cwd is not None:
            options["cwd"] = command.cwd
        if command.budget is not None:
            options["start_new_session"] = os.name != "nt"
            options["creationflags"] = (
                subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
            )
        elif os.name == "nt":
            options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            options["start_new_session"] = True
        if tree is not None:
            from .windows.settings import CREATE_SUSPENDED

            options["creationflags"] |= CREATE_SUSPENDED
        process = subprocess.Popen(arguments, **options)
        if tree is not None:
            try:
                tree.attach(process)
                tree.resume(process.pid)
            except BaseException as error:
                try:
                    cleanup = self._stop_tree(
                        process,
                        deadline=time.monotonic() + GIT_TREE_CLEANUP_SECONDS,
                        tree=tree,
                    )
                except (OSError, subprocess.TimeoutExpired):
                    cleanup = False
                if not isinstance(error, Exception):
                    error.cleanup_verified = cleanup
                    raise
                if not cleanup:
                    raise GitCommandCleanupError() from None
                raise
        return process

    @contextmanager
    def _read_process_tree(self):
        """Own a Windows job for budgeted reads; other profiles use their own containment."""
        tree = None
        if os.name == "nt":
            from .windows.tree import WindowsProcessTree

            tree = WindowsProcessTree()
        try:
            yield tree
        finally:
            if tree is not None and not tree.close():
                error = sys.exc_info()[1]
                if error is not None and not isinstance(error, Exception):
                    error.cleanup_verified = False
                else:
                    raise GitCommandCleanupError() from None

    def _execute_budgeted(self, command, arguments, environment):
        """Spool and actively observe a read budget without buffering child output."""
        budget = command.budget
        with TemporaryFile() as output, self._read_process_tree() as tree:
            process = self._start_process(
                command, arguments, environment, output, subprocess.DEVNULL, tree=tree
            )
            deadline = min(
                time.monotonic() + command.context.timeout, budget.operation_deadline
            )
            cleanup_verified = None
            try:
                while process.poll() is None:
                    if (
                        output.tell() > budget.stdout_limit
                        or time.monotonic() > deadline
                    ):
                        raise GitCommandLimitExceeded()
                    if budget.check_budget is not None:
                        budget.check_budget()
                    time.sleep(budget.poll_seconds)
                if tree is not None:
                    cleanup_verified = self._stop_tree(
                        process,
                        deadline=time.monotonic() + GIT_TREE_CLEANUP_SECONDS,
                        tree=tree,
                    )
                    if not cleanup_verified:
                        raise GitCommandCleanupError()
                output.seek(0)
                data = output.read(budget.stdout_limit + 1)
                return subprocess.CompletedProcess(
                    arguments, process.returncode, data, b""
                )
            except BaseException as error:
                if cleanup_verified is None:
                    try:
                        cleanup_verified = self._stop_tree(
                            process,
                            deadline=time.monotonic() + GIT_TREE_CLEANUP_SECONDS,
                            tree=tree,
                        )
                    except (OSError, subprocess.TimeoutExpired):
                        cleanup_verified = False
                if not isinstance(error, Exception):
                    error.cleanup_verified = cleanup_verified
                    raise
                if not cleanup_verified:
                    raise GitCommandCleanupError() from None
                if isinstance(error, GitCommandLimitExceeded):
                    error.cleanup_verified = True
                raise

    def _stop_tree(self, process, *, deadline=None, tree=None) -> bool:
        """Use profile-specific substep bounds or one shared read-cleanup deadline."""
        cleanup_verified = False
        if tree is not None:
            cleanup_verified = tree.terminate(deadline)
        elif os.name == "nt":
            try:
                killed = subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=self._cleanup_timeout(deadline),
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
            process.communicate(timeout=self._cleanup_timeout(deadline))
        except subprocess.TimeoutExpired:
            for pipe in (process.stdout, process.stderr):
                if pipe is not None:
                    pipe.close()
            try:
                process.wait(timeout=self._cleanup_timeout(deadline))
            except subprocess.TimeoutExpired:
                cleanup_verified = False
        return cleanup_verified

    @staticmethod
    def _cleanup_timeout(deadline):
        """Select a per-substep wait or the remaining shared read-cleanup budget."""
        return (
            GIT_TREE_CLEANUP_SECONDS
            if deadline is None
            else max(0.0, deadline - time.monotonic())
        )
