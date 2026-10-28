"""Verify authentication responses and persist private connection state."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from urllib.error import HTTPError
from urllib.error import URLError
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.request import HTTPSHandler
from urllib.request import Request
from urllib.request import build_opener
from uuid import uuid4
import csv
import json
import jwt
import laomedo.host.credentials.siwc.settings as _siwc_settings
import laomedo.host.credentials.siwc.errors as _siwc_errors
import os
import secrets
import ssl
import subprocess
import time
import truststore


def _tls_context():
    """Verify with the OS certificate store, without a process-wide SSL patch."""
    context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    return context


def _https_json(url: str, *, fields: dict | None = None) -> dict:
    import laomedo.host.credentials.siwc.connection as _siwc_connection

    parts = urlsplit(url)
    if (
        parts.scheme != "https"
        or parts.hostname != "auth.openai.com"
        or parts.username
        or parts.password
        or parts.fragment
    ):
        raise _siwc_errors.AuthError("auth_endpoint_untrusted")
    body = urlencode(fields).encode() if fields is not None else None
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    try:
        with build_opener(
            HTTPSHandler(context=_tls_context()), _siwc_connection._NoRedirect()
        ).open(Request(url, data=body, headers=headers), timeout=20) as response:
            result = json.load(response)
    except _siwc_errors.AuthError:
        raise
    except HTTPError as exc:
        # Status is safe to report; never include the URL, headers, or body.
        status = exc.code if type(exc.code) is int and 400 <= exc.code <= 599 else 0
        exc.close()
        raise _siwc_errors.AuthError(f"auth_http_{status}") from None
    except URLError as exc:
        if isinstance(exc.reason, ssl.SSLCertVerificationError):
            raise _siwc_errors.AuthError("auth_tls_verify_failed") from None
        raise _siwc_errors.AuthError("auth_transport_failed") from None
    except ssl.SSLCertVerificationError:
        raise _siwc_errors.AuthError("auth_tls_verify_failed") from None
    except (TimeoutError, OSError):
        raise _siwc_errors.AuthError("auth_transport_failed") from None
    except (ValueError, TypeError):
        raise _siwc_errors.AuthError("auth_response_invalid") from None
    except Exception:
        raise _siwc_errors.AuthError("auth_exchange_failed") from None
    if not isinstance(result, dict):
        raise _siwc_errors.AuthError("auth_response_invalid")
    return result


def _verify_id_token(token: str, client_id: str, nonce: str) -> dict:
    try:
        discovery = _https_json(
            _siwc_settings.AUTH_ORIGIN + "/.well-known/openid-configuration"
        )
        jwks_uri = discovery.get("jwks_uri")
        parts = urlsplit(jwks_uri)
        if (
            parts.scheme != "https"
            or parts.hostname != "auth.openai.com"
            or parts.username
            or parts.password
            or parts.fragment
        ):
            raise _siwc_errors.AuthError("auth_jwks_untrusted")
        key = (
            jwt.PyJWKClient(jwks_uri, ssl_context=_tls_context())
            .get_signing_key_from_jwt(token)
            .key
        )
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=client_id,
            issuer=_siwc_settings.AUTH_ORIGIN,
            options={"require": ["exp", "iss", "aud", "sub"]},
        )
        if not isinstance(claims.get("sub"), str) or not secrets.compare_digest(
            str(claims.get("nonce", "")), nonce
        ):
            raise _siwc_errors.AuthError("auth_identity_invalid")
        return claims
    except _siwc_errors.AuthError:
        raise
    except Exception:
        raise _siwc_errors.AuthError("auth_identity_invalid") from None


def _revoke(refresh_token: str, client_id: str) -> bool:
    import laomedo.host.credentials.siwc.connection as _siwc_connection

    discovery = _https_json(
        _siwc_settings.AUTH_ORIGIN + "/.well-known/openid-configuration"
    )
    endpoint = discovery.get("revocation_endpoint")
    parts = urlsplit(endpoint)
    if (
        parts.scheme != "https"
        or parts.hostname != "auth.openai.com"
        or parts.username
        or parts.password
        or parts.fragment
    ):
        raise _siwc_errors.AuthError("auth_revocation_endpoint_untrusted")
    data = urlencode(
        {
            "token": refresh_token,
            "token_type_hint": "refresh_token",
            "client_id": client_id,
        }
    ).encode()
    with build_opener(
        HTTPSHandler(context=_tls_context()), _siwc_connection._NoRedirect()
    ).open(
        Request(
            endpoint,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ),
        timeout=20,
    ) as response:
        return response.status == 200


def _atomic_private(path: Path, value: dict) -> None:
    pending = path.with_name(path.name + ".pending-" + uuid4().hex)
    data = json.dumps(value, sort_keys=True).encode("utf-8")
    fd = os.open(pending, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def _outside_git(path: Path) -> Path:
    original = path.expanduser().absolute()
    if any(parent.is_symlink() for parent in (original, *original.parents)):
        raise _siwc_errors.AuthError("auth_store_symlink_rejected")
    path = original.resolve()
    if any((parent / ".git").exists() for parent in (path, *path.parents)):
        raise _siwc_errors.AuthError("auth_store_must_be_outside_git")
    return path


def _restrict_windows_directory(path: Path) -> None:
    if os.name != "nt":
        os.chmod(path, 0o700)
        return
    identity = subprocess.run(
        ["whoami", "/user", "/fo", "csv", "/nh"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    if identity.returncode:
        raise _siwc_errors.AuthError("auth_store_permissions_unverified")
    rows = list(csv.reader(identity.stdout.splitlines()))
    if len(rows) != 1 or len(rows[0]) != 2 or not rows[0][1].startswith("S-"):
        raise _siwc_errors.AuthError("auth_store_permissions_unverified")
    sid = rows[0][1]
    result = subprocess.run(
        ["icacls", str(path), "/inheritance:r", "/grant:r", "*" + sid + ":(OI)(CI)F"],
        capture_output=True,
        text=True,
        timeout=15,
    )
    if result.returncode:
        raise _siwc_errors.AuthError("auth_store_permissions_unverified")


@contextmanager
def _locked(path: Path):
    fd = os.open(path, os.O_RDWR, 0o600)
    try:
        os.lseek(fd, 0, os.SEEK_SET)
        if os.name == "nt":
            import msvcrt

            deadline = time.monotonic() + 35
            while True:
                try:
                    msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                    break
                except OSError:
                    if time.monotonic() >= deadline:
                        raise _siwc_errors.AuthError(
                            "auth_refresh_lock_unavailable"
                        ) from None
                    time.sleep(0.1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_EX)
        try:
            yield
        finally:
            os.lseek(fd, 0, os.SEEK_SET)
            if os.name == "nt":
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
