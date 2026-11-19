"""Fixed bounded login policy, independent of inference and runner readiness."""

ATTEMPT_SECONDS = 180
MAX_CONNECTIONS = 32
NATIVE_AUTH_CLEANUP_SECONDS = 20
LOGIN_FAILURE_CATEGORIES = frozenset(
    {
        "auth_state_mismatch",
        "auth_consent_denied",
        "auth_callback_failed",
        "auth_client_mismatch",
        "auth_code_missing",
        "auth_account_mismatch",
        "auth_scope_missing",
        "auth_token_response_invalid",
        "auth_identity_invalid",
        "auth_exchange_failed",
        "auth_response_invalid",
        "auth_tls_verify_failed",
        "auth_transport_failed",
        "auth_jwks_untrusted",
        "auth_refresh_lock_unavailable",
        "provider_account_mismatch",
        "provider_connection_changed",
        "provider_connection_busy",
    }
)
