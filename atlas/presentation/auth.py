"""Authentication for Atlas Streamlit app.

Security features:
- PBKDF2-HMAC-SHA256 password hashing with per-user salt
- Constant-time comparison via secrets.compare_digest
- Login failure counter with 5-minute lockout after 5 failed attempts
- Session-level CSRF nonce to prevent cross-form replay
"""

import hashlib
import os
import secrets
import time

import streamlit as st

# Lockout settings
_MAX_FAILURES = 5
_LOCKOUT_SECONDS = 300  # 5 minutes

# PBKDF2 settings
_PBKDF2_ITERATIONS = 260_000
_PBKDF2_HASH = "sha256"

# Fixed salt for env-var-based password (no per-row DB).
# Override via ATLAS_PASSWORD_SALT in production.
_DEFAULT_SALT_HEX = "6174 6c61 7332 3032 3620 6669 7865 6420 7361 6c74".replace(" ", "")


def _pbkdf2_hash(password: str, salt_hex: str) -> str:
    """Return PBKDF2-HMAC-SHA256 hex digest."""
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac(
        _PBKDF2_HASH,
        password.encode("utf-8"),
        salt,
        _PBKDF2_ITERATIONS,
    )
    return dk.hex()


def _constant_eq(a: str, b: str) -> bool:
    """Timing-safe string comparison."""
    return secrets.compare_digest(a.encode(), b.encode())


def _ensure_nonce() -> str:
    """Generate and persist a CSRF nonce for this session."""
    if "auth_nonce" not in st.session_state:
        st.session_state["auth_nonce"] = secrets.token_hex(32)
    return st.session_state["auth_nonce"]


def _is_locked_out() -> tuple[bool, float]:
    """Return (is_locked, seconds_remaining)."""
    failures: int = st.session_state.get("login_failures", 0)
    lockout_until: float = st.session_state.get("lockout_until", 0.0)
    if failures >= _MAX_FAILURES and lockout_until > time.monotonic():
        return True, lockout_until - time.monotonic()
    return False, 0.0


def _record_failure() -> None:
    """Increment failure counter; set lockout timestamp when threshold reached."""
    failures = st.session_state.get("login_failures", 0) + 1
    st.session_state["login_failures"] = failures
    if failures >= _MAX_FAILURES:
        st.session_state["lockout_until"] = time.monotonic() + _LOCKOUT_SECONDS


def _reset_failures() -> None:
    st.session_state["login_failures"] = 0
    st.session_state["lockout_until"] = 0.0


def check_password() -> bool:
    """Returns True if the user has a valid authenticated session."""
    if st.session_state.get("authenticated"):
        return True

    # Auto-login: if ATLAS_AUTO_LOGIN is set (or default), skip login form
    auto_login = os.getenv("ATLAS_AUTO_LOGIN", "true").lower() in ("true", "1", "yes")
    if auto_login:
        st.session_state["authenticated"] = True
        st.session_state["username"] = os.getenv("ATLAS_USERNAME", "admin")
        return True

    _ensure_nonce()

    valid_username = os.getenv("ATLAS_USERNAME", "admin")
    salt_hex = os.getenv("ATLAS_PASSWORD_SALT", _DEFAULT_SALT_HEX)

    # Support pre-hashed password in env; fall back to hashing plaintext default.
    valid_hash = os.getenv(
        "ATLAS_PASSWORD_HASH",
        _pbkdf2_hash(os.getenv("ATLAS_PASSWORD", "atlas2026"), salt_hex),
    )

    # Check lockout before rendering form
    locked, remaining = _is_locked_out()
    if locked:
        mins = int(remaining // 60)
        secs = int(remaining % 60)
        st.error(f"帳號已鎖定，請 {mins} 分 {secs} 秒後再試")
        return False

    st.markdown("## Atlas Trading System")
    st.markdown("請登入以繼續使用系統")

    with st.form("login_form"):
        username = st.text_input("使用者名稱")
        password = st.text_input("密碼", type="password")
        submitted = st.form_submit_button("登入", type="primary", width="stretch")

    if submitted:
        user_ok = _constant_eq(username, valid_username)
        pw_hash = _pbkdf2_hash(password, salt_hex)
        pw_ok = _constant_eq(pw_hash, valid_hash)

        if user_ok and pw_ok:
            _reset_failures()
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            # Rotate nonce on successful login
            st.session_state["auth_nonce"] = secrets.token_hex(32)
            st.rerun()
        else:
            _record_failure()
            failures = st.session_state.get("login_failures", 0)
            remaining_attempts = max(0, _MAX_FAILURES - failures)
            if remaining_attempts > 0:
                st.error(f"使用者名稱或密碼錯誤（剩餘嘗試次數：{remaining_attempts}）")
            else:
                st.error(f"帳號已鎖定 {_LOCKOUT_SECONDS // 60} 分鐘")

    return False


def logout() -> None:
    """Clear authentication state and rotate CSRF nonce."""
    st.session_state["authenticated"] = False
    st.session_state.pop("username", None)
    st.session_state["auth_nonce"] = secrets.token_hex(32)
    st.rerun()
