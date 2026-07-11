"""Unit tests for atlas.presentation.auth (upgraded security model)."""

import hashlib
import importlib
import os
import secrets
import time
from unittest.mock import MagicMock, patch

# Disable auto-login for all auth tests
os.environ["ATLAS_AUTO_LOGIN"] = "false"


# ---------------------------------------------------------------------------
# Helpers — replicate module internals for independent verification
# ---------------------------------------------------------------------------

_PBKDF2_ITERATIONS = 260_000
_DEFAULT_SALT_HEX = "6174 6c61 7332 3032 3620 6669 7865 6420 7361 6c74".replace(" ", "")


def _pbkdf2(password: str, salt_hex: str = _DEFAULT_SALT_HEX) -> str:
    salt = bytes.fromhex(salt_hex)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return dk.hex()


def _make_session(**kwargs) -> dict:
    return dict(kwargs)


def _mock_form_ctx():
    """Return a context-manager mock suitable for `with st.form(...)`."""
    return MagicMock(__enter__=lambda s: s, __exit__=MagicMock(return_value=False))


# ---------------------------------------------------------------------------
# Password hashing quality
# ---------------------------------------------------------------------------

def test_pbkdf2_consistency():
    assert _pbkdf2("atlas2026") == _pbkdf2("atlas2026")


def test_pbkdf2_uniqueness():
    assert _pbkdf2("atlas2026") != _pbkdf2("wrong_password")


def test_pbkdf2_different_salts_differ():
    salt2 = "deadbeef" * 8  # 64 hex chars
    assert _pbkdf2("atlas2026") != _pbkdf2("atlas2026", salt_hex=salt2)


def test_pbkdf2_output_is_hex_string():
    result = _pbkdf2("atlas2026")
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


# ---------------------------------------------------------------------------
# check_password — already authenticated
# ---------------------------------------------------------------------------

def test_check_password_returns_true_when_authenticated():
    mock_session = {"authenticated": True}

    with patch("streamlit.session_state", mock_session):
        import atlas.presentation.auth as auth
        importlib.reload(auth)
        result = auth.check_password()

    assert result is True


# ---------------------------------------------------------------------------
# check_password — not authenticated, no submission
# ---------------------------------------------------------------------------

def test_check_password_returns_false_when_not_authenticated():
    mock_session = {}

    with (
        patch("streamlit.session_state", mock_session),
        patch("streamlit.markdown"),
        patch("streamlit.error"),
        patch("streamlit.form", return_value=_mock_form_ctx()),
        patch("streamlit.text_input", return_value=""),
        patch("streamlit.form_submit_button", return_value=False),
    ):
        import atlas.presentation.auth as auth
        importlib.reload(auth)
        result = auth.check_password()

    assert result is False


# ---------------------------------------------------------------------------
# CSRF nonce
# ---------------------------------------------------------------------------

def test_nonce_created_on_first_call():
    """A CSRF nonce must be written into session state on first check_password."""
    mock_session = {}

    with (
        patch("streamlit.session_state", mock_session),
        patch("streamlit.markdown"),
        patch("streamlit.error"),
        patch("streamlit.form", return_value=_mock_form_ctx()),
        patch("streamlit.text_input", return_value=""),
        patch("streamlit.form_submit_button", return_value=False),
    ):
        import atlas.presentation.auth as auth
        importlib.reload(auth)
        auth.check_password()

    assert "auth_nonce" in mock_session
    assert len(mock_session["auth_nonce"]) == 64  # 32-byte hex


def test_nonce_stable_across_calls():
    """Repeated calls without login must not rotate the nonce."""
    mock_session = {}

    with (
        patch("streamlit.session_state", mock_session),
        patch("streamlit.markdown"),
        patch("streamlit.error"),
        patch("streamlit.form", return_value=_mock_form_ctx()),
        patch("streamlit.text_input", return_value=""),
        patch("streamlit.form_submit_button", return_value=False),
    ):
        import atlas.presentation.auth as auth
        importlib.reload(auth)
        auth.check_password()
        nonce1 = mock_session["auth_nonce"]
        auth.check_password()
        nonce2 = mock_session["auth_nonce"]

    assert nonce1 == nonce2


# ---------------------------------------------------------------------------
# Login failure counter
# ---------------------------------------------------------------------------

def test_failure_counter_increments():
    """Each failed attempt must increment login_failures."""
    mock_session = {}

    with (
        patch("streamlit.session_state", mock_session),
        patch("streamlit.markdown"),
        patch("streamlit.error"),
        patch("streamlit.form", return_value=_mock_form_ctx()),
        patch("streamlit.text_input", side_effect=["admin", "wrong"]),
        patch("streamlit.form_submit_button", return_value=True),
    ):
        import atlas.presentation.auth as auth
        importlib.reload(auth)
        auth.check_password()

    assert mock_session.get("login_failures", 0) == 1


def test_lockout_applied_after_max_failures():
    """After 5 failures lockout_until must be set in the future."""
    mock_session = {"login_failures": 4}  # one more will trigger lockout

    with (
        patch("streamlit.session_state", mock_session),
        patch("streamlit.markdown"),
        patch("streamlit.error"),
        patch("streamlit.form", return_value=_mock_form_ctx()),
        patch("streamlit.text_input", side_effect=["admin", "wrong"]),
        patch("streamlit.form_submit_button", return_value=True),
    ):
        import atlas.presentation.auth as auth
        importlib.reload(auth)
        auth.check_password()

    assert mock_session.get("login_failures", 0) >= 5
    assert mock_session.get("lockout_until", 0) > time.monotonic()


def test_locked_out_session_returns_false_without_form():
    """A locked-out session must show error and return False immediately."""
    mock_session = {
        "login_failures": 5,
        "lockout_until": time.monotonic() + 300,
    }

    error_called = []

    with (
        patch("streamlit.session_state", mock_session),
        patch("streamlit.markdown"),
        patch("streamlit.error", side_effect=lambda msg: error_called.append(msg)),
        # form should NOT be rendered — if it is the test will fail on missing
        # text_input mock
        patch("streamlit.form", side_effect=AssertionError("form must not render during lockout")),
    ):
        import atlas.presentation.auth as auth
        importlib.reload(auth)
        result = auth.check_password()

    assert result is False
    assert error_called, "st.error must be called when locked out"


def test_successful_login_resets_failure_counter():
    """A correct login must clear login_failures and lockout_until."""
    mock_session = {"login_failures": 3, "lockout_until": 0.0}

    with (
        patch("streamlit.session_state", mock_session),
        patch("streamlit.markdown"),
        patch("streamlit.error"),
        patch("streamlit.form", return_value=_mock_form_ctx()),
        patch("streamlit.text_input", side_effect=["admin", "atlas2026"]),
        patch("streamlit.form_submit_button", return_value=True),
        patch("streamlit.rerun"),
    ):
        import atlas.presentation.auth as auth
        importlib.reload(auth)
        auth.check_password()

    assert mock_session.get("login_failures") == 0
    assert mock_session.get("lockout_until") == 0.0
    assert mock_session.get("authenticated") is True


# ---------------------------------------------------------------------------
# logout
# ---------------------------------------------------------------------------

def test_logout_clears_authenticated():
    mock_session = {"authenticated": True, "username": "admin", "auth_nonce": "abc"}

    with (
        patch("streamlit.session_state", mock_session),
        patch("streamlit.rerun"),
    ):
        import atlas.presentation.auth as auth
        importlib.reload(auth)
        auth.logout()

    assert mock_session["authenticated"] is False


def test_logout_removes_username():
    mock_session = {"authenticated": True, "username": "admin", "auth_nonce": "abc"}

    with (
        patch("streamlit.session_state", mock_session),
        patch("streamlit.rerun"),
    ):
        import atlas.presentation.auth as auth
        importlib.reload(auth)
        auth.logout()

    assert "username" not in mock_session


def test_logout_rotates_nonce():
    """logout must replace the nonce to invalidate the old session token."""
    old_nonce = "a" * 64
    mock_session = {"authenticated": True, "auth_nonce": old_nonce}

    with (
        patch("streamlit.session_state", mock_session),
        patch("streamlit.rerun"),
    ):
        import atlas.presentation.auth as auth
        importlib.reload(auth)
        auth.logout()

    assert mock_session.get("auth_nonce") != old_nonce
    assert mock_session.get("auth_nonce") is not None


def test_logout_tolerates_missing_username():
    mock_session = {"authenticated": True}

    with (
        patch("streamlit.session_state", mock_session),
        patch("streamlit.rerun"),
    ):
        import atlas.presentation.auth as auth
        importlib.reload(auth)
        auth.logout()  # must not raise

    assert mock_session["authenticated"] is False
