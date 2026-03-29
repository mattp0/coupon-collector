"""Tests for database.py.

get_connection() reads from st.secrets and calls psycopg2.connect — both are
mocked so these tests run without a real database or Streamlit context.
"""

from unittest.mock import MagicMock, patch


def _make_conn_mock():
    cursor = MagicMock()
    conn = MagicMock()
    conn.cursor.return_value = cursor
    return conn, cursor


# ---------------------------------------------------------------------------
# get_connection
# ---------------------------------------------------------------------------

def test_get_connection_reads_url_from_secrets():
    mock_conn = MagicMock()
    with (
        patch("database.st") as mock_st,
        patch("database.psycopg2.connect", return_value=mock_conn) as mock_connect,
    ):
        mock_st.secrets = {"database": {"url": "postgresql://test:test@localhost/test"}}

        from database import get_connection
        result = get_connection()

        mock_connect.assert_called_once_with("postgresql://test:test@localhost/test")
        assert result is mock_conn


# ---------------------------------------------------------------------------
# init_db
# ---------------------------------------------------------------------------

def test_init_db_creates_all_tables():
    conn, cursor = _make_conn_mock()
    with (
        patch("database.st") as mock_st,
        patch("database.psycopg2.connect", return_value=conn),
    ):
        mock_st.secrets = {"database": {"url": "postgresql://test"}}

        from database import init_db
        init_db()

        executed_sql = " ".join(
            call_args.args[0]
            for call_args in cursor.execute.call_args_list
        )

        for table in ["manufacturers", "coupons", "settings", "reports", "report_coupons"]:
            assert table in executed_sql, f"Expected CREATE TABLE for '{table}'"


def test_init_db_seeds_default_settings():
    conn, cursor = _make_conn_mock()
    with (
        patch("database.st") as mock_st,
        patch("database.psycopg2.connect", return_value=conn),
    ):
        mock_st.secrets = {"database": {"url": "postgresql://test"}}

        from database import init_db
        init_db()

        executed_sql = " ".join(
            call_args.args[0]
            for call_args in cursor.execute.call_args_list
        )

        for key in ["company_name", "company_address", "handling_fee"]:
            assert key in executed_sql, f"Expected default setting '{key}' to be seeded"


def test_init_db_commits_and_closes():
    conn, cursor = _make_conn_mock()
    with (
        patch("database.st") as mock_st,
        patch("database.psycopg2.connect", return_value=conn),
    ):
        mock_st.secrets = {"database": {"url": "postgresql://test"}}

        from database import init_db
        init_db()

        conn.commit.assert_called_once()
        cursor.close.assert_called_once()
        conn.close.assert_called_once()