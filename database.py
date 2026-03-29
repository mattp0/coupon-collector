import psycopg2
import streamlit as st
from psycopg2.extensions import connection as PgConnection


def get_connection() -> PgConnection:
    """Return a connection to the Postgres database.

    The connection string is read from Streamlit secrets:

        [database]
        url = "postgresql://user:password@host:5432/dbname"

    To point the app at a different Postgres instance (e.g. self-hosted),
    update that single value in secrets.toml or the Streamlit Cloud secrets
    manager. No application code needs to change.
    """
    url: str = st.secrets["database"]["url"]
    return psycopg2.connect(url)


def init_db() -> None:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS manufacturers (
            id      SERIAL PRIMARY KEY,
            name    TEXT UNIQUE NOT NULL,
            address TEXT NOT NULL DEFAULT ''
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS coupons (
            id             SERIAL PRIMARY KEY,
            manufacturer   TEXT NOT NULL,
            coupon_id      TEXT NOT NULL,
            amount         NUMERIC(10, 2) NOT NULL,
            handling_fee   BOOLEAN NOT NULL DEFAULT FALSE,
            collected_date DATE NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL DEFAULT ''
        )
    """)

    cursor.execute("""
        INSERT INTO settings (key, value) VALUES
            ('company_name',    ''),
            ('company_address', ''),
            ('handling_fee',    '0.08')
        ON CONFLICT (key) DO NOTHING
    """)

    conn.commit()
    cursor.close()
    conn.close()
