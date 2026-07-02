"""Simple authentication for Atlas Streamlit app."""

import hashlib
import os

import streamlit as st


def check_password() -> bool:
    """Returns True if the user has entered a correct password."""

    def _hash(password: str) -> str:
        return hashlib.sha256(password.encode()).hexdigest()

    # Get credentials from env vars
    valid_username = os.getenv("ATLAS_USERNAME", "admin")
    valid_password_hash = os.getenv(
        "ATLAS_PASSWORD_HASH",
        _hash(os.getenv("ATLAS_PASSWORD", "atlas2026")),
    )

    if st.session_state.get("authenticated"):
        return True

    # Show login form
    st.markdown("## 🔐 Atlas Trading System")
    st.markdown("請登入以繼續使用系統")

    with st.form("login_form"):
        username = st.text_input("使用者名稱")
        password = st.text_input("密碼", type="password")
        submitted = st.form_submit_button("登入", type="primary", use_container_width=True)

    if submitted:
        if username == valid_username and _hash(password) == valid_password_hash:
            st.session_state["authenticated"] = True
            st.session_state["username"] = username
            st.rerun()
        else:
            st.error("使用者名稱或密碼錯誤")

    return False


def logout() -> None:
    """Clear authentication state."""
    st.session_state["authenticated"] = False
    st.session_state.pop("username", None)
    st.rerun()
