# Bestand: core/frontend/auth.py
"""
Authentication module voor Sanskriti Setu Streamlit frontend.
Handles JWT-based authentication met session state management.

CRITICAL FIX C1: Business logic gescheiden van UI logic voor testbaarheid.
CRITICAL FIX C2: Gebruikt st.rerun() i.p.v. deprecated st.experimental_rerun().
"""

import logging
from typing import Any, cast

import requests

st: Any | None = None  # TODO(TYPE): replace Any with concrete type
STREAMLIT_AVAILABLE = False
try:
    import streamlit as _st_import

    st = _st_import
    STREAMLIT_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency for Streamlit frontend
    pass

from src.core.frontend.config import settings

logger = logging.getLogger(__name__)


# ============================================================================
# BUSINESS LOGIC (Testbaar zonder Streamlit)
# ============================================================================


def authenticate_user(
    email: str, password: str, timeout: int = 10
) -> dict[str, object]:
    """
    Authenticate user via backend API.

    Args:
        email: User email address
        password: User password
        timeout: Request timeout in seconds

    Returns:
        dict: {"success": True, "token": "...", "email": "..."}
              or {"success": False, "error": "..."}

    Note:
        CRITICAL FIX C1: Separated from UI for unit testing.
        Uses synchronous requests.post (correct for Streamlit's sync model).
    """
    try:
        response = requests.post(
            f"{settings.API_BASE_URL}/api/v1/auth/token",
            data={"username": email, "password": password},
            timeout=timeout,
        )

        if response.status_code == 200:
            token_data = cast(dict[str, object], response.json())
            logger.info("Successful login for user: [REDACTED]")
            return {
                "success": True,
                "token": cast(str, token_data["access_token"]),
                "email": email,
            }
        elif response.status_code == 401:
            logger.warning("Failed login attempt for user: [REDACTED]")
            return {"success": False, "error": "Invalid email or password"}
        else:
            logger.error("Login failed with status %d", response.status_code)
            return {
                "success": False,
                "error": f"Login failed with status code: {response.status_code}",
            }

    except requests.exceptions.Timeout:
        logger.error("Login request timeout for user: [REDACTED]")
        return {"success": False, "error": "Request timeout. Please try again."}
    except requests.exceptions.ConnectionError:
        logger.error("Connection error during login for user: [REDACTED]")
        return {"success": False, "error": "Could not connect to API server"}
    except requests.exceptions.RequestException as e:
        logger.error("Request exception during login: %s: %s", type(e).__name__, e, exc_info=True)
        return {"success": False, "error": f"Connection error: {str(e)}"}


def is_authenticated() -> bool:
    """
    Check if user is authenticated by verifying token in session state.

    Returns:
        bool: True if user has valid access_token in session state
    """
    if not STREAMLIT_AVAILABLE or st is None:
        return False
    return "access_token" in st.session_state and st.session_state["access_token"]


def get_auth_headers() -> dict[str, str]:
    """
    Returns authorization headers if user is authenticated.

    Returns:
        dict: {"Authorization": "Bearer <token>"} or {}
    """
    if not STREAMLIT_AVAILABLE or st is None:
        return {}
    if is_authenticated():
        return {"Authorization": f"Bearer {st.session_state['access_token']}"}
    return {}


def logout_user() -> None:
    """
    Log out user by clearing session state.

    Note:
        Clears access_token and user_email from session state.
        Caller should trigger st.rerun() after calling this.
    """
    if not STREAMLIT_AVAILABLE or st is None:
        return
    if "access_token" in st.session_state:
        del st.session_state["access_token"]
    if "user_email" in st.session_state:
        del st.session_state["user_email"]
    logger.info("User logged out")


# ============================================================================
# UI LOGIC (Streamlit-specific)
# ============================================================================


def login_form() -> None:
    """
    Displays the login form and handles the login process.

    CRITICAL FIX C2: Uses st.rerun() instead of deprecated st.experimental_rerun().
    """
    if not STREAMLIT_AVAILABLE or st is None:
        raise RuntimeError("Streamlit is not installed")
    st.title(settings.APP_TITLE)
    st.markdown("### Gelieve in te loggen om door te gaan")

    with st.form("login_form"):
        email = st.text_input("Email", key="login_email")
        password = st.text_input("Password", type="password", key="login_password")
        submitted = st.form_submit_button("Login")

        if submitted:
            if not email or not password:
                st.error("Vul alstublieft zowel email als wachtwoord in.")
                return

            with st.spinner("Bezig met inloggen..."):
                result = authenticate_user(email, password, timeout=settings.API_TIMEOUT)

                if result["success"]:
                    # Store in session state
                    st.session_state["access_token"] = result["token"]
                    st.session_state["user_email"] = result["email"]

                    st.success("Succesvol ingelogd!")

                    # CRITICAL FIX C2: Use st.rerun() instead of st.experimental_rerun()
                    st.rerun()
                else:
                    st.error(f"Login mislukt: {result['error']}")


def display_logout() -> None:
    """
    Displays user info and a logout button in the sidebar.

    CRITICAL FIX C2: Uses st.rerun() instead of deprecated st.experimental_rerun().
    """
    if not STREAMLIT_AVAILABLE or st is None:
        raise RuntimeError("Streamlit is not installed")
    if is_authenticated():
        user_email = st.session_state.get("user_email", "Gebruiker")
        st.sidebar.success(f"Ingelogd als: {user_email}")

        if st.sidebar.button("Uitloggen"):
            logout_user()
            st.success("U bent uitgelogd.")

            # CRITICAL FIX C2: Use st.rerun() instead of st.experimental_rerun()
            st.rerun()
