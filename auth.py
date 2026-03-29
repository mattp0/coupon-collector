import streamlit as st


def require_login():
    """Gate the entire application behind Google SSO.

    On Streamlit Cloud, configure the following in the app's Secrets manager
    (or locally in .streamlit/secrets.toml):

        [auth]
        redirect_uri    = "https://your-app.streamlit.app/oauth2callback"
        cookie_secret   = "<random string, e.g. from secrets.token_hex(32)>"

        [auth.google]
        client_id       = "<from Google Cloud Console>"
        client_secret   = "<from Google Cloud Console>"

    Optionally restrict access to specific email addresses by setting
    ALLOWED_EMAILS below. Leave the set empty to allow any Google account.

    Returns the authenticated user object (user.email, user.name, user.picture).
    Calls st.stop() if the user is not authenticated.
    """
    ALLOWED_EMAILS: set[str] = {
        "matthew.r.perry25@gmail.com",
        "jennaperry307@gmail.com",
    }

    if not st.user.is_logged_in:
        st.login("google")
        st.stop()
 
    if ALLOWED_EMAILS and st.user.email not in ALLOWED_EMAILS:
        st.error(
            f"Access denied. The account {st.user.email} is not authorised to use this application."
        )
        st.stop()

    return st.user