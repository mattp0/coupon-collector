from contextlib import contextmanager
from datetime import date
from typing import Optional

import pandas as pd
import psycopg2
import streamlit as st
from psycopg2.extensions import connection as PgConnection


class DuplicateNameError(Exception):
    pass


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


@contextmanager
def managed_connection():
    """Context manager that guarantees a connection is closed on exit."""
    conn = get_connection()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_cursor(conn):
    """Context manager that yields a cursor, commits on success, rolls back on error."""
    cursor = conn.cursor()
    try:
        yield cursor
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cursor.close()


def init_db() -> None:
    with managed_connection() as conn:
        with get_cursor(conn) as cursor:
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
                    status           TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'sent', 'responded')),
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

            cursor.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'reports_status_check'
                          AND conrelid = 'reports'::regclass
                    ) THEN
                        ALTER TABLE reports
                            ADD CONSTRAINT reports_status_check
                            CHECK (status IN ('draft', 'sent', 'responded'));
                    END IF;
                END $$
            """)

            for table in ("manufacturers", "coupons", "settings", "reports", "report_coupons"):
                cursor.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
                cursor.execute(f"""
                    DO $$
                    BEGIN
                        IF NOT EXISTS (
                            SELECT 1 FROM pg_policies
                            WHERE schemaname = 'public'
                              AND tablename  = '{table}'
                              AND policyname = 'allow_all'
                        ) THEN
                            CREATE POLICY allow_all ON {table} FOR ALL USING (true) WITH CHECK (true);
                        END IF;
                    END $$
                """)


# ---------------------------------------------------------------------------
# Manufacturers
# ---------------------------------------------------------------------------

def get_manufacturer_names(conn) -> list[str]:
    return pd.read_sql("SELECT name FROM manufacturers ORDER BY name", conn)["name"].tolist()


def get_manufacturers(conn) -> pd.DataFrame:
    return pd.read_sql("SELECT id, name, address FROM manufacturers ORDER BY name", conn)


def get_manufacturer_address(conn, name: str) -> str:
    row = pd.read_sql(
        "SELECT address FROM manufacturers WHERE name = %s", conn, params=(name,)
    )
    return row["address"].iloc[0] if not row.empty else ""


def upsert_manufacturer_name(conn, name: str) -> None:
    with get_cursor(conn) as cur:
        cur.execute(
            "INSERT INTO manufacturers (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
            (name,),
        )


def add_manufacturer(conn, name: str, address: str) -> None:
    try:
        with get_cursor(conn) as cur:
            cur.execute(
                "INSERT INTO manufacturers (name, address) VALUES (%s, %s)",
                (name, address),
            )
    except psycopg2.errors.UniqueViolation:
        raise DuplicateNameError(name)


def update_manufacturer(conn, id: int, name: str, address: str) -> None:
    try:
        with get_cursor(conn) as cur:
            cur.execute(
                "UPDATE manufacturers SET name = %s, address = %s WHERE id = %s",
                (name, address, id),
            )
    except psycopg2.errors.UniqueViolation:
        raise DuplicateNameError(name)


def delete_manufacturer(conn, id: int) -> None:
    with get_cursor(conn) as cur:
        cur.execute("DELETE FROM manufacturers WHERE id = %s", (id,))


# ---------------------------------------------------------------------------
# Coupons
# ---------------------------------------------------------------------------

def get_recent_coupons(conn) -> pd.DataFrame:
    return pd.read_sql(
        """SELECT id, collected_date, manufacturer, coupon_id, amount, handling_fee
           FROM coupons ORDER BY id DESC LIMIT 50""",
        conn,
    )


def get_coupons_for_period(conn, manufacturer: str, start: date, end: date) -> pd.DataFrame:
    return pd.read_sql(
        """SELECT coupon_id, amount, handling_fee, collected_date
           FROM coupons
           WHERE manufacturer = %s AND collected_date BETWEEN %s AND %s
           ORDER BY coupon_id, collected_date""",
        conn,
        params=(manufacturer, start, end),
    )


def add_coupon(
    conn,
    manufacturer: str,
    coupon_id: str,
    amount: float,
    handling_fee: bool,
    collected_date: date,
) -> None:
    with get_cursor(conn) as cur:
        cur.execute(
            """INSERT INTO coupons (manufacturer, coupon_id, amount, handling_fee, collected_date)
               VALUES (%s, %s, %s, %s, %s)""",
            (manufacturer, coupon_id, round(amount, 2), handling_fee, collected_date),
        )


def update_coupon(
    conn,
    id: int,
    manufacturer: str,
    coupon_id: str,
    amount: float,
    handling_fee: bool,
    collected_date: date,
) -> None:
    with get_cursor(conn) as cur:
        cur.execute(
            """UPDATE coupons
               SET manufacturer = %s, coupon_id = %s, amount = %s,
                   handling_fee = %s, collected_date = %s
               WHERE id = %s""",
            (manufacturer, coupon_id, round(amount, 2), handling_fee, collected_date, id),
        )


def delete_coupon(conn, id: int) -> None:
    with get_cursor(conn) as cur:
        cur.execute("DELETE FROM coupons WHERE id = %s", (id,))


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_settings(conn) -> dict:
    return (
        pd.read_sql("SELECT key, value FROM settings", conn)
        .set_index("key")["value"]
        .to_dict()
    )


def save_settings(conn, company_name: str, company_address: str, handling_fee: float) -> None:
    with get_cursor(conn) as cur:
        for key, val in [
            ("company_name",    company_name),
            ("company_address", company_address),
            ("handling_fee",    str(round(handling_fee, 2))),
        ]:
            cur.execute(
                """INSERT INTO settings (key, value) VALUES (%s, %s)
                   ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                (key, val),
            )


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------

def get_reports(conn) -> pd.DataFrame:
    return pd.read_sql(
        """SELECT id, ref_number, manufacturer, period_start, period_end,
                  generated_date, coupon_count, grand_total, status,
                  sent_date, response_date, payment_amount, check_reference, notes
           FROM reports
           ORDER BY generated_date DESC, id DESC""",
        conn,
    )


def save_report(
    conn,
    ref_number: str,
    manufacturer: str,
    period_start: date,
    period_end: date,
    total_face: float,
    total_handling: float,
    grand_total: float,
    coupons: pd.DataFrame,
) -> int:
    """Insert a report and its coupon snapshot. Returns the new report id."""
    with get_cursor(conn) as cur:
        cur.execute(
            """INSERT INTO reports
                   (ref_number, manufacturer, period_start, period_end,
                    generated_date, coupon_count, total_face, total_handling,
                    grand_total, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'draft')
               RETURNING id""",
            (
                ref_number,
                manufacturer,
                period_start,
                period_end,
                date.today(),
                len(coupons),
                round(total_face, 2),
                round(total_handling, 2),
                round(grand_total, 2),
            ),
        )
        report_id: int = cur.fetchone()[0]

        for _, row in coupons.iterrows():
            cur.execute(
                """INSERT INTO report_coupons
                       (report_id, coupon_id, amount, handling_fee, collected_date)
                   VALUES (%s, %s, %s, %s, %s)""",
                (
                    report_id,
                    str(row["coupon_id"]),
                    float(row["amount"]),
                    bool(row["handling_fee"]),
                    row["collected_date"],
                ),
            )

    return report_id


def delete_draft_report(conn, id: int) -> None:
    with get_cursor(conn) as cur:
        cur.execute("DELETE FROM reports WHERE id = %s AND status = 'draft'", (id,))


def update_report_status(
    conn,
    id: int,
    status: str,
    sent_date,
    response_date,
    payment_amount: Optional[float],
    check_reference: Optional[str],
    notes: Optional[str],
) -> None:
    with get_cursor(conn) as cur:
        cur.execute(
            """UPDATE reports
               SET status          = %s,
                   sent_date       = %s,
                   response_date   = %s,
                   payment_amount  = %s,
                   check_reference = %s,
                   notes           = %s
               WHERE id = %s""",
            (
                status,
                sent_date or None,
                response_date or None,
                round(payment_amount, 2) if payment_amount else None,
                check_reference.strip() or None if check_reference else None,
                notes.strip() or None if notes else None,
                id,
            ),
        )


def get_report_for_pdf(conn, report_id: int) -> Optional[tuple]:
    """Fetch the report row, its coupon snapshot, and manufacturer address.

    Returns (report_row, snapshot_df, mfr_address) or None if not found.
    """
    report = pd.read_sql(
        "SELECT * FROM reports WHERE id = %s", conn, params=(report_id,)
    )
    if report.empty:
        return None

    snapshot = pd.read_sql(
        """SELECT coupon_id, amount, handling_fee, collected_date
           FROM report_coupons WHERE report_id = %s
           ORDER BY coupon_id, collected_date""",
        conn,
        params=(report_id,),
    )

    row = report.iloc[0]
    mfr_row = pd.read_sql(
        "SELECT address FROM manufacturers WHERE name = %s",
        conn,
        params=(row["manufacturer"],),
    )
    mfr_address = mfr_row["address"].iloc[0] if not mfr_row.empty else ""

    return row, snapshot, mfr_address
