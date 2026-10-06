"""Minimal WebAuthn assertion verification (ES256) without third-party packages.

Only what the local approval authority needs: verify that an authenticator
holding a registered P-256 key signed ``authenticatorData || SHA-256(clientDataJSON)``
for an exact challenge, origin and relying party, with user presence and user
verification. No registration ceremony, attestation or other algorithms.
"""

from __future__ import annotations

import base64
from hashlib import sha256
import hmac
import json

# NIST P-256 (secp256r1) domain parameters.
P = 0xFFFFFFFF00000001000000000000000000000000FFFFFFFFFFFFFFFFFFFFFFFF
A = P - 3
B = 0x5AC635D8AA3A93E7B3EBBD55769886BC651D06B0CC53B0F63BCE3C3E27D2604B
N = 0xFFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551
G = (0x6B17D1F2E12C4247F8BCE6E563A440F277037D812DEB33A0F4A13945D898C296,
     0x4FE342E2FE1A7F9B8EE7EB4A7C0F9E162BCE33576B315ECECBB6406837BF51F5)

FLAG_USER_PRESENT = 0x01
FLAG_USER_VERIFIED = 0x04


class AssertionError_(ValueError):
    """Raised with a stable, nonsecret reason code."""


def b64url_decode(value: str) -> bytes:
    if not isinstance(value, str) or not value or "=" in value:
        raise AssertionError_("invalid_base64url")
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (ValueError, TypeError):
        raise AssertionError_("invalid_base64url") from None


def b64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def on_curve(point) -> bool:
    x, y = point
    return 0 <= x < P and 0 <= y < P and (y * y - (x * x * x + A * x + B)) % P == 0


def _add(p1, p2):
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    (x1, y1), (x2, y2) = p1, p2
    if x1 == x2 and (y1 + y2) % P == 0:
        return None
    if p1 == p2:
        slope = (3 * x1 * x1 + A) * pow(2 * y1, -1, P) % P
    else:
        slope = (y2 - y1) * pow(x2 - x1, -1, P) % P
    x3 = (slope * slope - x1 - x2) % P
    return x3, (slope * (x1 - x3) - y1) % P


def multiply(k: int, point):
    result, addend = None, point
    while k:
        if k & 1:
            result = _add(result, addend)
        addend = _add(addend, addend)
        k >>= 1
    return result


def _der_integer(data: bytes, offset: int) -> tuple[int, int]:
    if offset + 2 > len(data) or data[offset] != 0x02:
        raise AssertionError_("invalid_signature_encoding")
    length = data[offset + 1]
    start, end = offset + 2, offset + 2 + length
    if length == 0 or length > 33 or end > len(data):
        raise AssertionError_("invalid_signature_encoding")
    value = data[start:end]
    if value[0] & 0x80 or (length > 1 and value[0] == 0 and not value[1] & 0x80):
        raise AssertionError_("invalid_signature_encoding")
    return int.from_bytes(value, "big"), end


def parse_der_signature(signature: bytes) -> tuple[int, int]:
    if len(signature) < 8 or signature[0] != 0x30 or signature[1] != len(signature) - 2:
        raise AssertionError_("invalid_signature_encoding")
    r, offset = _der_integer(signature, 2)
    s, offset = _der_integer(signature, offset)
    if offset != len(signature):
        raise AssertionError_("invalid_signature_encoding")
    return r, s


def verify_es256(public_point, message: bytes, signature: bytes) -> bool:
    if not on_curve(public_point):
        raise AssertionError_("invalid_public_key")
    r, s = parse_der_signature(signature)
    if not (1 <= r < N and 1 <= s < N):
        return False
    digest = int.from_bytes(sha256(message).digest(), "big")
    w = pow(s, -1, N)
    point = _add(multiply(digest * w % N, G), multiply(r * w % N, public_point))
    return point is not None and point[0] % N == r


def verify_assertion(*, public_point, rp_id: str, origin: str, challenge: bytes,
                     authenticator_data: bytes, client_data_json: bytes,
                     signature: bytes) -> int:
    """Verify one assertion and return the authenticator's signature counter."""
    try:
        client = json.loads(client_data_json.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise AssertionError_("invalid_client_data") from None
    if not isinstance(client, dict) or client.get("type") != "webauthn.get":
        raise AssertionError_("wrong_ceremony_type")
    if not hmac.compare_digest(b64url_decode(client.get("challenge", "")), challenge):
        raise AssertionError_("challenge_mismatch")
    if client.get("origin") != origin:
        raise AssertionError_("origin_mismatch")
    if len(authenticator_data) < 37:
        raise AssertionError_("invalid_authenticator_data")
    if not hmac.compare_digest(authenticator_data[:32], sha256(rp_id.encode("utf-8")).digest()):
        raise AssertionError_("rp_id_mismatch")
    flags = authenticator_data[32]
    if not flags & FLAG_USER_PRESENT:
        raise AssertionError_("user_not_present")
    if not flags & FLAG_USER_VERIFIED:
        raise AssertionError_("user_not_verified")
    signed = authenticator_data + sha256(client_data_json).digest()
    if not verify_es256(public_point, signed, signature):
        raise AssertionError_("signature_invalid")
    return int.from_bytes(authenticator_data[33:37], "big")
