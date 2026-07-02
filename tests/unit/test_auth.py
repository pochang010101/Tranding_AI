"""Unit tests for atlas.presentation.auth."""

import hashlib
from unittest.mock import MagicMock, patch


def _hash(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Password hashing
# ---------------------------------------------------------------------------

def test_hash_consistency():
    """Same input must always produce the same digest."""
    assert _hash("atlas2026") == _hash("atlas2026")


def test_hash_uniqueness():
    """Different passwords must not collide."""
    assert _hash("atlas2026") != _hash("wrong_password")


def test_hash_is_hex_string():
    """Output should be a 64-char hex string (SHA-256)."""
    result = _hash("atlas2026")
    assert len(result) == 64
    assert all(c in "0123456789abcdef" for c in result)


# ---------------------------------------------------------------------------
# check_password — not authenticated
# ---------------------------------------------------------------------------

def test_check_password_returns_false_when_not_authenticated():
    """check_password must return False when session is not authenticated."""
    mock_session = {}

    with (
        patch("streamlit.session_state", mock_session),
        patch("streamlit.markdown"),
        patch("streamlit.form", return_value=MagicMock(__enter__=lambda s: s, __exit__=MagicMock(return_value=False))),
        patch("streamlit.text_input", return_value=""),
        patch("streamlit.form_submit_button", return_value=False),
    ):
        from atlas.presentation.auth import check_password
        result = check_password()

    assert result is False


def test_check_password_returns_true_when_authenticated():
    """check_password must short-circuit True when already authenticated."""
    mock_session = {"authenticated": True}

    with patch("streamlit.session_state", mock_session):
        from atlas.presentation.auth import check_password
        result = check_password()

    assert result is True


# ---------------------------------------------------------------------------
# logout
# ---------------------------------------------------------------------------

def test_logout_clears_authenticated():
    """logout must set authenticated to False."""
    mock_session = {"authenticated": True, "username": "admin"}

    with (
        patch("streamlit.session_state", mock_session),
        patch("streamlit.rerun"),
    ):
        from atlas.presentation.auth import logout
        logout()

    assert mock_session["authenticated"] is False


def test_logout_removes_username():
    """logout must remove username from session state."""
    mock_session = {"authenticated": True, "username": "admin"}

    with (
        patch("streamlit.session_state", mock_session),
        patch("streamlit.rerun"),
    ):
        from atlas.presentation.auth import logout
        logout()

    assert "username" not in mock_session


def test_logout_tolerates_missing_username():
    """logout must not raise if username key is absent."""
    mock_session = {"authenticated": True}

    with (
        patch("streamlit.session_state", mock_session),
        patch("streamlit.rerun"),
    ):
        from atlas.presentation.auth import logout
        logout()  # should not raise

    assert mock_session["authenticated"] is False
