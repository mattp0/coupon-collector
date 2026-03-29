# Coupon Report Manager

A web application for logging manufacturer coupons collected at a small business and generating per-manufacturer PDF reports with handling fee tracking.

## Features

- Log coupons by manufacturer with face value, handling fee flag, and collection date
- Edit or delete individual coupon entries
- Generate PDF reports per manufacturer for a selected date range
- Report history with status tracking: Draft, Sent, and Response Received
- Record manufacturer responses including payment amount, check reference, and notes
- Regenerate any historical PDF from the original coupon snapshot
- Google SSO authentication with an optional email allowlist

## Requirements

- Python 3.11+
- A PostgreSQL database (Supabase free tier recommended for cloud deployment)
- A Google Cloud OAuth 2.0 client (for authentication)

## Local Setup

Install dependencies:

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt  # for running tests only
```

Copy the secrets template and fill in your values:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Run the app:

```bash
streamlit run app.py
```

The app will open in your browser at `http://localhost:8501`. On first run it creates all required database tables automatically.

## Configuration

All configuration lives in `.streamlit/secrets.toml`, which is never committed to version control. See `.streamlit/secrets.toml.example` for the full reference.

Key values to set:

| Key | Description |
|---|---|
| `database.url` | PostgreSQL connection string |
| `auth.client_id` | Google OAuth client ID |
| `auth.client_secret` | Google OAuth client secret |
| `auth.cookie_secret` | Random string for session cookies — generate with `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `auth.redirect_uri` | OAuth callback URL for your deployment |
| `auth.server_metadata_url` | Always `https://accounts.google.com/.well-known/openid-configuration` |
| `auth.allowed_emails` | Comma-separated list of permitted Google accounts. Omit to allow any Google account. |

## Keeping Allowed Emails Private

If your repository is public, do not put email addresses in code or committed files. Instead, set `allowed_emails` in one of two places:

**Streamlit Cloud:** Add it to the Secrets manager under App settings > Secrets in the `[auth]` block. It is encrypted and never exposed in logs or the UI.

**Self-hosted or local:** Set the `ALLOWED_EMAILS` environment variable:

```bash
export ALLOWED_EMAILS="alice@example.com,bob@example.com"
streamlit run app.py
```

The application checks Streamlit secrets first, then falls back to the environment variable. If neither is set, any authenticated Google account is permitted.

## Deployment on Streamlit Cloud

1. Push the repository to GitHub.
2. Connect the repo at [share.streamlit.io](https://share.streamlit.io).
3. Set the main file path to `app.py`.
4. Add all secrets from `secrets.toml.example` under App settings > Secrets.
5. Streamlit Cloud redeploys automatically on every push to `main`.

To require CI checks to pass before deployment triggers, add a branch protection rule on `main` in GitHub under Settings > Branches requiring the `test` status check.

## Migrating to Self-Hosted

When your self-hosted environment is ready, update a single value:

```toml
[database]
url = "postgresql://user:password@your-server:5432/dbname"
```

No application code changes are required.

## Running Tests

```bash
pytest
```

Tests mock all database and Streamlit dependencies and run without a live database or Streamlit context.

## Health Monitoring

Streamlit exposes a health endpoint at `/_stcore/health`. Point an uptime monitor such as UptimeRobot at:

```
https://your-app.streamlit.app/_stcore/health
```

Set the check interval to 5 minutes and configure email alerts for downtime.

## Project Structure

```
app.py              Application entry point and all page functions
auth.py             Google SSO gate and email allowlist logic
database.py         Database connection and schema initialisation
pdf_generator.py    PDF report generation
requirements.txt    Production dependencies
requirements-dev.txt  Development and test dependencies
conftest.py         Pytest path configuration
pytest.ini          Pytest settings
tests/
    test_app.py
    test_database.py
    test_pdf_generator.py
.streamlit/
    secrets.toml.example  Configuration reference (safe to commit)
.github/
    workflows/
        ci.yml      GitHub Actions CI workflow
```