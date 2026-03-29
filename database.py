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
        CREATE TABLE IF NOT EXISTS reports (
            id               SERIAL PRIMARY KEY,
            ref_number       TEXT NOT NULL,
            manufacturer     TEXT NOT NULL,
            period_start     DATE NOT NULL,
            period_end       DATE NOT NULL,
            generated_date   DATE NOT NULL,
            coupon_count     INTEGER NOT NULL,
            total_face       NUMERIC(10, 2) NOT NULL,
            total_handling   NUMERIC(10, 2) NOT NULL,
            grand_total      NUMERIC(10, 2) NOT NULL,
            status           TEXT NOT NULL DEFAULT 'draft',
            sent_date        DATE,
            response_date    DATE,
            payment_amount   NUMERIC(10, 2),
            check_reference  TEXT,
            notes            TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS report_coupons (
            id             SERIAL PRIMARY KEY,
            report_id      INTEGER NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
            coupon_id      TEXT NOT NULL,
            amount         NUMERIC(10, 2) NOT NULL,
            handling_fee   BOOLEAN NOT NULL DEFAULT FALSE,
            collected_date DATE NOT NULL
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