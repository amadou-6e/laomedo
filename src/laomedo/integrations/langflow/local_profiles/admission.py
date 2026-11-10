"""Read-only admission before migrations or creation of an internal identity."""

from contextlib import closing
from pathlib import Path
import os
import secrets
import sqlite3

from alembic.script import ScriptDirectory
from langflow import __file__ as langflow_file
from langflow.services.database.models import User
from lfx.services.settings.constants import LEGACY_DEFAULT_SUPERUSER_PASSWORD
from pydantic import SecretStr, ValidationError

from laomedo.integrations.langflow.local_profiles.errors import ProfileError
from laomedo.integrations.langflow.local_profiles.models import ProfileRuntimeMarker
from laomedo.integrations.langflow.local_profiles.settings import SYSTEM_PROFILE_NAME


class ProfileRuntimeAdmission:
    """Admit only owned fresh state or the recognized current profile schema.

    No database mutation, repair, account promotion or password reset occurs here.
    A failed check leaves the database unchanged and serving must not start.
    """

    def __init__(self, runtime_root: Path):
        self.root = runtime_root.resolve()
        self.database = self.root / "langflow" / "flow.db"
        try:
            self.marker = ProfileRuntimeMarker.model_validate_json(
                (self.root / "local-profiles.json").read_text(encoding="utf-8-sig")
            )
        except (OSError, ValidationError):
            raise ProfileError("profile_setup_unavailable") from None

    def verify_settings(self, service):
        """Check effective auth policy, not just the launcher's environment."""
        auth = service.auth_settings
        if (
            auth.AUTO_LOGIN
            or auth.skip_auth_auto_login
            or auth.ENABLE_SIGNUP
            or not auth.NEW_USER_IS_ACTIVE
            or auth.EXTERNAL_AUTH_ENABLED
            or auth.API_KEY_SOURCE != "db"
            or os.environ.get("LANGFLOW_API_KEY")
            or str(service.settings.database_url)
            != "sqlite:///" + self.database.as_posix()
        ):
            raise ProfileError("profile_setup_unavailable")

    def verify_database(self, auth) -> bool:
        """Return True only for admitted fresh state; reject partial/unknown DBs."""
        if self.database.is_symlink():
            raise ProfileError("profile_setup_unavailable")
        if not self.database.exists():
            return True
        try:
            with closing(
                sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)
            ) as db:
                if db.execute("PRAGMA quick_check").fetchone() != ("ok",):
                    raise ProfileError("profile_setup_unavailable")
                tables = {
                    row[0]
                    for row in db.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    )
                }
                if not tables:
                    return True
                expected = User.metadata.tables
                if (
                    not set(expected).issubset(tables)
                    or "alembic_version" not in tables
                ):
                    raise ProfileError("profile_setup_unavailable")
                for table, definition in expected.items():
                    quoted = table.replace('"', '""')
                    columns = {
                        row[1] for row in db.execute(f'PRAGMA table_info("{quoted}")')
                    }
                    if not set(definition.columns.keys()).issubset(columns):
                        raise ProfileError("profile_setup_unavailable")
                scripts = ScriptDirectory(str(Path(langflow_file).parent / "alembic"))
                actual_heads = {
                    row[0]
                    for row in db.execute("SELECT version_num FROM alembic_version")
                }
                if actual_heads != set(scripts.get_heads()):
                    raise ProfileError("profile_setup_unavailable")
                users = db.execute(
                    'SELECT id, username, password, is_active, is_superuser FROM "user"'
                ).fetchall()
                system = [row for row in users if row[1] == SYSTEM_PROFILE_NAME]
                if len(system) != 1 or system[0][3:] != (1, 1):
                    raise ProfileError("profile_setup_unavailable")
                if any(row[4] and row[0] != system[0][0] for row in users):
                    raise ProfileError("profile_setup_unavailable")
                if any(
                    row[0] != system[0][0]
                    and row[1].casefold() == SYSTEM_PROFILE_NAME.casefold()
                    for row in users
                ):
                    raise ProfileError("profile_setup_unavailable")
                if db.execute(
                    "SELECT 1 FROM apikey WHERE user_id = ? LIMIT 1", (system[0][0],)
                ).fetchone():
                    raise ProfileError("profile_setup_unavailable")
                try:
                    if auth.pwd_context.verify(
                        LEGACY_DEFAULT_SUPERUSER_PASSWORD.get_secret_value(),
                        system[0][2],
                    ):
                        raise ProfileError("profile_setup_unavailable")
                except (TypeError, ValueError):
                    raise ProfileError("profile_setup_unavailable") from None
                names = [row[1].casefold() for row in users]
                if len(set(names)) != len(names):
                    raise ProfileError("profile_setup_unavailable")
                return False
        except (sqlite3.Error, OSError):
            raise ProfileError("profile_setup_unavailable") from None

    def prepare(self, service):
        """Supply an in-memory startup value only after read-only admission."""
        self.verify_settings(service)
        self.verify_database(service.auth_settings)
        service.auth_settings.SUPERUSER = SYSTEM_PROFILE_NAME
        service.auth_settings.SUPERUSER_PASSWORD = SecretStr(secrets.token_urlsafe(48))
