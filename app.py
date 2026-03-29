from datetime import date

import pandas as pd
import psycopg2
import streamlit as st

from auth import require_login
from database import get_connection, init_db
from pdf_generator import generate_pdf

NEW_MANUFACTURER_SENTINEL = "Add new manufacturer..."


def page_enter_coupons() -> None:
    st.title("Enter Coupons")

    conn = get_connection()
    manufacturers = pd.read_sql(
        "SELECT name FROM manufacturers ORDER BY name", conn
    )["name"].tolist()
    options = manufacturers + [NEW_MANUFACTURER_SENTINEL]

    with st.form("coupon_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            mfr_select = st.selectbox("Manufacturer", options)
            if mfr_select == NEW_MANUFACTURER_SENTINEL:
                manufacturer = st.text_input("New manufacturer name")
            else:
                manufacturer = mfr_select
            coupon_id = st.text_input("Coupon ID")

        with col2:
            amount = st.number_input("Face Value ($)", min_value=0.0, step=0.01, format="%.2f")
            handling_fee = st.checkbox("Subject to handling fee ($0.08)")
            collected_date = st.date_input("Date Collected", value=date.today())

        submitted = st.form_submit_button("Add Coupon", use_container_width=True)

        if submitted:
            if not manufacturer or manufacturer == NEW_MANUFACTURER_SENTINEL:
                st.error("Please enter a manufacturer name.")
            elif not coupon_id.strip():
                st.error("Please enter a Coupon ID.")
            elif amount <= 0:
                st.error("Face value must be greater than $0.00.")
            else:
                cursor = conn.cursor()
                if mfr_select == NEW_MANUFACTURER_SENTINEL and manufacturer.strip():
                    cursor.execute(
                        "INSERT INTO manufacturers (name) VALUES (%s) ON CONFLICT (name) DO NOTHING",
                        (manufacturer.strip(),),
                    )
                cursor.execute(
                    """INSERT INTO coupons (manufacturer, coupon_id, amount, handling_fee, collected_date)
                       VALUES (%s, %s, %s, %s, %s)""",
                    (
                        manufacturer.strip(),
                        coupon_id.strip(),
                        round(amount, 2),
                        handling_fee,
                        collected_date,
                    ),
                )
                conn.commit()
                cursor.close()
                st.success(f"Coupon {coupon_id} added for {manufacturer}.")

    st.divider()
    st.subheader("Recent Entries")

    recent = pd.read_sql(
        """SELECT collected_date, manufacturer, coupon_id, amount, handling_fee
           FROM coupons ORDER BY id DESC LIMIT 20""",
        conn,
    )

    if recent.empty:
        st.info("No coupons entered yet.")
    else:
        recent["amount"] = recent["amount"].apply(lambda x: f"${x:.2f}")
        recent["handling_fee"] = recent["handling_fee"].apply(lambda x: "Yes" if x else "No")
        recent.columns = ["Date", "Manufacturer", "Coupon ID", "Face Value", "Handling Fee"]
        st.dataframe(recent, use_container_width=True, hide_index=True)

    conn.close()


def page_generate_reports() -> None:
    st.title("Generate Reports")

    conn = get_connection()
    settings = pd.read_sql(
        "SELECT key, value FROM settings", conn
    ).set_index("key")["value"].to_dict()

    manufacturers = pd.read_sql(
        "SELECT name FROM manufacturers ORDER BY name", conn
    )["name"].tolist()

    if not manufacturers:
        st.warning("No manufacturers found. Add coupons or manufacturers first.")
        conn.close()
        st.stop()

    col1, col2 = st.columns(2)
    with col1:
        selected_mfr = st.selectbox("Manufacturer", manufacturers)
        start_date = st.date_input("Start Date", value=date(date.today().year, 1, 1))
    with col2:
        end_date = st.date_input("End Date", value=date.today())
        today_str = date.today().strftime("%Y%m%d")
        auto_ref = f"REF-{today_str}-{selected_mfr[:3].upper()}"
        ref_number = st.text_input("Reference Number", value=auto_ref)

    df = pd.read_sql(
        """SELECT coupon_id, amount, handling_fee, collected_date
           FROM coupons
           WHERE manufacturer = %s
             AND collected_date BETWEEN %s AND %s
           ORDER BY coupon_id, collected_date""",
        conn,
        params=(selected_mfr, start_date, end_date),
    )

    if df.empty:
        st.info("No coupons found for this manufacturer in the selected date range.")
        conn.close()
        st.stop()

    st.subheader(f"Preview - {selected_mfr}")
    st.caption(f"Period: {start_date} to {end_date}  |  {len(df)} coupon(s)")

    display = df.copy()
    display["amount"] = display["amount"].apply(lambda x: f"${x:.2f}")
    display["handling_fee"] = display["handling_fee"].apply(lambda x: "$0.08" if x else "-")
    display.columns = ["Coupon ID", "Face Value", "Handling Fee", "Date"]
    st.dataframe(display, use_container_width=True, hide_index=True)

    handling_fee_rate = float(settings.get("handling_fee", "0.08"))
    total_face = df["amount"].sum()
    total_handling = df["handling_fee"].apply(lambda x: handling_fee_rate if x else 0.0).sum()
    grand_total = total_face + total_handling

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Face Value", f"${total_face:.2f}")
    c2.metric("Total Handling Fees", f"${total_handling:.2f}")
    c3.metric("Grand Total", f"${grand_total:.2f}")

    st.divider()

    mfr_row = pd.read_sql(
        "SELECT address FROM manufacturers WHERE name = %s",
        conn,
        params=(selected_mfr,),
    )
    mfr_address = mfr_row["address"].iloc[0] if not mfr_row.empty else ""

    if st.button("Generate PDF Report", use_container_width=True, type="primary"):
        pdf_bytes = generate_pdf(
            company_settings=settings,
            manufacturer=selected_mfr,
            manufacturer_address=mfr_address or "",
            ref_number=ref_number,
            start_date=start_date,
            end_date=end_date,
            coupons=df,
        )
        filename = f"coupon_report_{selected_mfr.replace(' ', '_')}_{today_str}.pdf"
        st.download_button(
            label="Download PDF",
            data=pdf_bytes,
            file_name=filename,
            mime="application/pdf",
            use_container_width=True,
        )

    conn.close()


def page_manage_manufacturers() -> None:
    st.title("Manage Manufacturers")

    conn = get_connection()

    with st.expander("Add Manufacturer", expanded=False):
        with st.form("add_mfr"):
            new_name = st.text_input("Manufacturer Name")
            new_address = st.text_area("Mailing Address (shown on report)")
            if st.form_submit_button("Add"):
                if not new_name.strip():
                    st.error("Name is required.")
                else:
                    try:
                        cursor = conn.cursor()
                        cursor.execute(
                            "INSERT INTO manufacturers (name, address) VALUES (%s, %s)",
                            (new_name.strip(), new_address.strip()),
                        )
                        conn.commit()
                        cursor.close()
                        st.success(f"Added {new_name}.")
                        st.rerun()
                    except psycopg2.errors.UniqueViolation:
                        conn.rollback()
                        st.error("A manufacturer with that name already exists.")

    manufacturers = pd.read_sql(
        "SELECT id, name, address FROM manufacturers ORDER BY name", conn
    )

    if manufacturers.empty:
        st.info("No manufacturers saved yet.")
    else:
        st.subheader("Saved Manufacturers")
        for _, row in manufacturers.iterrows():
            with st.expander(row["name"]):
                with st.form(f"edit_mfr_{row['id']}"):
                    edit_name = st.text_input("Name", value=row["name"])
                    edit_addr = st.text_area("Mailing Address", value=row["address"] or "")
                    col_save, col_del = st.columns([3, 1])
                    with col_save:
                        if st.form_submit_button("Save Changes"):
                            cursor = conn.cursor()
                            cursor.execute(
                                "UPDATE manufacturers SET name = %s, address = %s WHERE id = %s",
                                (edit_name.strip(), edit_addr.strip(), int(row["id"])),
                            )
                            conn.commit()
                            cursor.close()
                            st.success("Saved.")
                            st.rerun()
                    with col_del:
                        if st.form_submit_button("Delete", type="secondary"):
                            cursor = conn.cursor()
                            cursor.execute(
                                "DELETE FROM manufacturers WHERE id = %s",
                                (int(row["id"]),),
                            )
                            conn.commit()
                            cursor.close()
                            st.warning(f"Deleted {row['name']}.")
                            st.rerun()

    conn.close()


def page_settings() -> None:
    st.title("Settings")
    st.caption("This information appears on every generated PDF report.")

    conn = get_connection()
    s = pd.read_sql(
        "SELECT key, value FROM settings", conn
    ).set_index("key")["value"].to_dict()

    with st.form("settings_form"):
        company_name = st.text_input("Company Name", value=s.get("company_name", ""))
        company_address = st.text_area("Company Address", value=s.get("company_address", ""))
        handling_fee_default = st.number_input(
            "Default Handling Fee ($)",
            value=float(s.get("handling_fee", "0.08")),
            step=0.01,
            format="%.2f",
        )

        if st.form_submit_button("Save Settings", use_container_width=True, type="primary"):
            cursor = conn.cursor()
            for key, val in [
                ("company_name",    company_name),
                ("company_address", company_address),
                ("handling_fee",    str(round(handling_fee_default, 2))),
            ]:
                cursor.execute(
                    """INSERT INTO settings (key, value) VALUES (%s, %s)
                       ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value""",
                    (key, val),
                )
            conn.commit()
            cursor.close()
            st.success("Settings saved.")

    conn.close()


def main() -> None:
    st.set_page_config(page_title="Coupon Report Manager", layout="wide")
    init_db()

    user = require_login()

    st.sidebar.title("Coupon Reports")
    st.sidebar.caption(f"Signed in as {user.email}")

    page = st.sidebar.radio(
        "Navigate",
        ["Enter Coupons", "Generate Reports", "Manage Manufacturers", "Settings"],
    )

    if st.sidebar.button("Sign out"):
        st.logout()

    if page == "Enter Coupons":
        page_enter_coupons()
    elif page == "Generate Reports":
        page_generate_reports()
    elif page == "Manage Manufacturers":
        page_manage_manufacturers()
    elif page == "Settings":
        page_settings()


if __name__ == "__main__":
    main()
