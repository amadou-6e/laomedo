"""Read-only account admission before upstream normal-login startup."""

from contextlib import closing
from pathlib import Path
import secrets
import sqlite3
from pydantic import SecretStr
from laomedo.integrations.langflow.normal_login.models import RuntimeMarker


class NormalLoginStartup:
    """Keep bootstrap separate from serving; never create or reset an account."""

    def __init__(self, runtime_root: Path):
        self.runtime_root = runtime_root.resolve()
        self.marker_path = self.runtime_root / "normal-login.json"
        self.marker = RuntimeMarker.model_validate_json(
            self.marker_path.read_text(encoding="utf-8-sig")
        )
        self.database = self.runtime_root / "langflow" / "flow.db"

    def _verify_administrator(
        self, username, auth_settings, default_username, legacy_password
    ):
        if not username or username == default_username:
            raise RuntimeError(
                "Bootstrap a non-default administrator before serving this app."
            )
        if not self.database.is_file() or self.database.is_symlink():
            raise RuntimeError(
                "Bootstrap database is missing or unsupported; do not start an empty app."
            )
        try:
            with closing(
                sqlite3.connect(self.database.as_uri() + "?mode=ro", uri=True)
            ) as db:
                row = db.execute(
                    'SELECT password, is_superuser, is_active FROM "user" WHERE username = ?',
                    (username,),
                ).fetchone()
        except sqlite3.Error:
            raise RuntimeError(
                "Bootstrap database could not be verified. Recheck the isolated setup."
            ) from None
        if row is None or row[1] != 1 or row[2] != 1:
            raise RuntimeError(
                "The named active administrator was not found; bootstrap has not succeeded."
            )
        try:
            legacy = auth_settings.pwd_context.verify(legacy_password, row[0])
        except (ValueError, TypeError):
            raise RuntimeError(
                "Administrator password format could not be verified safely."
            ) from None
        if legacy:
            raise RuntimeError(
                "The legacy default administrator password is refused; correct the account before serving."
            )

    def confirm_bootstrap(
        self, username, auth_settings, default_username, legacy_password
    ):
        """Verify the actual CLI result; its exit status alone is insufficient."""
        self._verify_administrator(
            username, auth_settings, default_username, legacy_password
        )
        marker = self.marker.model_copy(
            update={"bootstrap_admin": username, "database": self.database}
        )
        temporary = self.marker_path.with_suffix(".pending")
        temporary.write_text(marker.model_dump_json(indent=2), encoding="utf-8")
        temporary.replace(self.marker_path)
        self.marker = marker

    def prepare(self, settings_service, default_username, legacy_password):
        """Provide only an in-memory startup value after read-only admission."""
        if not self.marker.bootstrap_admin or self.marker.database is None:
            raise RuntimeError(
                "Run Bootstrap and verify the administrator before Serve."
            )
        expected_url = "sqlite:///" + self.database.as_posix()
        if (
            self.marker.database != self.database
            or str(settings_service.settings.database_url) != expected_url
        ):
            raise RuntimeError(
                "Effective database does not match the verified bootstrap database."
            )
        auth_settings = settings_service.auth_settings
        if (
            auth_settings.AUTO_LOGIN
            or auth_settings.skip_auth_auto_login
            or auth_settings.ENABLE_SIGNUP
        ):
            raise RuntimeError(
                "Normal login requires auto-login, bypass and public signup disabled."
            )
        self._verify_administrator(
            self.marker.bootstrap_admin,
            auth_settings,
            default_username,
            legacy_password,
        )
        auth_settings.SUPERUSER = self.marker.bootstrap_admin
        auth_settings.SUPERUSER_PASSWORD = SecretStr(secrets.token_urlsafe(48))
