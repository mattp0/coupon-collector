import os

import streamlit as st


def _load_allowed_emails() -> set[str]:
    """Load the email allowlist from Streamlit secrets or environment.

    In Streamlit Cloud, set this in the Secrets manager:

        [auth]
        allowed_emails = "alice@example.com,bob@example.com"

    Locally, you can set the environment variable instead:

        ALLOWED_EMAILS="alice@example.com,bob@example.com"

    If neither is set, any authenticated Google account is permitted.
    """
    raw = ""

    try:
        raw = st.secrets.get("auth", {}).get("allowed_emails", "")
    except Exception:
        pass

    if not raw:
        raw = os.environ.get("ALLOWED_EMAILS", "")

    if not raw:
        return set()

    return {email.strip().lower() for email in raw.split(",") if email.strip()}


def require_login():
    """Gate the entire application behind Google SSO.

    Returns the authenticated user object (user.email, user.name).
    Calls st.stop() if the user is not authenticated or not authorised.
    """
    if not st.user.is_logged_in:
        st.login("google")
        st.stop()

    allowed_emails = _load_allowed_emails()

    if allowed_emails and st.user.email.lower() not in allowed_emails:
        st.error(
            f"Access denied. The account {st.user.email} is not authorised "
            "to use this application."
        )
        st.stop()

    return st.user