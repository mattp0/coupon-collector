from datetime import date
from typing import Optional

import pandas as pd
import psycopg2
import streamlit as st

from auth import require_login
from database import get_connection, init_db
from pdf_generator import generate_pdf

NEW_MANUFACTURER_SENTINEL = "Add new manufacturer..."

STATUS_LABELS = {
    "draft":     "Draft",
    "sent":      "Sent",
    "responded": "Response Received",
}


def _save_report(
    conn,
    ref_number: str,
    manufacturer: str,
    period_start: date,
    period_end: date,
    total_face: float,
    total_handling: float,
    grand_total: float,
    coupons: pd.DataFrame,
    handling_fee_val: float,
) -> int:
    """Insert a report and its coupon snapshot. Returns the new report id."""
    cursor = conn.cursor()
    cursor.execute(
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
    report_id: int = cursor.fetchone()[0]

    for _, row in coupons.iterrows():
        cursor.execute(
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

    conn.commit()
    cursor.close()
    return report_id


def _build_pdf_from_snapshot(report_id: int, conn, settings: dict) -> Optional[bytes]:
    """Regenerate a PDF from the stored report_coupons snapshot."""
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

    return generate_pdf(
        company_settings=settings,
        manufacturer=row["manufacturer"],
        manufacturer_address=mfr_address,
        ref_number=row["ref_number"],
        start_date=row["period_start"],
        end_date=row["period_end"],
        coupons=snapshot,
    )


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
        """SELECT id, collected_date, manufacturer, coupon_id, amount, handling_fee
           FROM coupons ORDER BY id DESC LIMIT 50""",
        conn,
    )

    if recent.empty:
        st.info("No coupons entered yet.")
    else:
        editing_id = st.session_state.get("editing_coupon_id")

        for _, row in recent.iterrows():
            row_id = int(row["id"])
            col_date, col_mfr, col_cid, col_amt, col_fee, col_edit, col_del = st.columns(
                [1.2, 1.5, 1.2, 0.8, 0.8, 0.6, 0.6]
            )
            col_date.write(str(row["collected_date"]))
            col_mfr.write(row["manufacturer"])
            col_cid.write(row["coupon_id"])
            col_amt.write(f"${float(row['amount']):.2f}")
            col_fee.write("Yes" if row["handling_fee"] else "No")

            if col_edit.button("Edit", key=f"edit_{row_id}"):
                st.session_state["editing_coupon_id"] = row_id
                st.rerun()

            if col_del.button("Delete", key=f"del_{row_id}"):
                cursor = conn.cursor()
                cursor.execute("DELETE FROM coupons WHERE id = %s", (row_id,))
                conn.commit()
                cursor.close()
                st.success("Coupon deleted.")
                st.rerun()

            if editing_id == row_id:
                with st.form(f"edit_form_{row_id}"):
                    st.caption(f"Editing coupon #{row_id}")
                    ecol1, ecol2 = st.columns(2)
                    with ecol1:
                        edit_mfr = st.selectbox(
                            "Manufacturer",
                            options,
                            index=options.index(row["manufacturer"]) if row["manufacturer"] in options else 0,
                            key=f"emfr_{row_id}",
                        )
                        edit_cid = st.text_input("Coupon ID", value=row["coupon_id"], key=f"ecid_{row_id}")
                    with ecol2:
                        edit_amt = st.number_input(
                            "Face Value ($)", value=float(row["amount"]),
                            min_value=0.0, step=0.01, format="%.2f", key=f"eamt_{row_id}",
                        )
                        edit_fee = st.checkbox(
                            "Subject to handling fee ($0.08)",
                            value=bool(row["handling_fee"]),
                            key=f"efee_{row_id}",
                        )
                        edit_date = st.date_input(
                            "Date Collected",
                            value=row["collected_date"],
                            key=f"edate_{row_id}",
                        )

                    save_col, cancel_col = st.columns([1, 1])
                    with save_col:
                        save = st.form_submit_button("Save Changes", use_container_width=True, type="primary")
                    with cancel_col:
                        cancel = st.form_submit_button("Cancel", use_container_width=True)

                    if save:
                        if not edit_cid.strip():
                            st.error("Coupon ID is required.")
                        elif edit_amt <= 0:
                            st.error("Face value must be greater than $0.00.")
                        else:
                            cursor = conn.cursor()
                            cursor.execute(
                                """UPDATE coupons
                                   SET manufacturer = %s, coupon_id = %s, amount = %s,
                                       handling_fee = %s, collected_date = %s
                                   WHERE id = %s""",
                                (
                                    edit_mfr.strip(),
                                    edit_cid.strip(),
                                    round(edit_amt, 2),
                                    edit_fee,
                                    edit_date,
                                    row_id,
                                ),
                            )
                            conn.commit()
                            cursor.close()
                            del st.session_state["editing_coupon_id"]
                            st.success("Coupon updated.")
                            st.rerun()

                    if cancel:
                        del st.session_state["editing_coupon_id"]
                        st.rerun()

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
    total_face = float(df["amount"].sum())
    total_handling = float(df["handling_fee"].apply(lambda x: handling_fee_rate if x else 0.0).sum())
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

        report_id = _save_report(
            conn=conn,
            ref_number=ref_number,
            manufacturer=selected_mfr,
            period_start=start_date,
            period_end=end_date,
            total_face=total_face,
            total_handling=total_handling,
            grand_total=grand_total,
            coupons=df,
            handling_fee_val=handling_fee_rate,
        )

        filename = f"coupon_report_{selected_mfr.replace(' ', '_')}_{today_str}.pdf"
        st.download_button(
            label="Download PDF",
            data=pdf_bytes,
            file_name=filename,
            mime="application/pdf",
            use_container_width=True,
        )
        st.info(f"Report saved to history (ID {report_id}).")

    conn.close()


def page_report_history() -> None:
    st.title("Report History")

    conn = get_connection()
    settings = pd.read_sql(
        "SELECT key, value FROM settings", conn
    ).set_index("key")["value"].to_dict()

    reports = pd.read_sql(
        """SELECT id, ref_number, manufacturer, period_start, period_end,
                  generated_date, coupon_count, grand_total, status,
                  sent_date, response_date, payment_amount, check_reference, notes
           FROM reports
           ORDER BY generated_date DESC, id DESC""",
        conn,
    )

    if reports.empty:
        st.info("No reports generated yet.")
        conn.close()
        return

    # Filter controls
    filter_col1, filter_col2 = st.columns(2)
    with filter_col1:
        all_mfrs = ["All"] + sorted(reports["manufacturer"].unique().tolist())
        filter_mfr = st.selectbox("Filter by manufacturer", all_mfrs)
    with filter_col2:
        all_statuses = ["All"] + [STATUS_LABELS[s] for s in ["draft", "sent", "responded"]]
        filter_status = st.selectbox("Filter by status", all_statuses)

    if filter_mfr != "All":
        reports = reports[reports["manufacturer"] == filter_mfr]
    if filter_status != "All":
        reverse_labels = {v: k for k, v in STATUS_LABELS.items()}
        reports = reports[reports["status"] == reverse_labels[filter_status]]

    st.caption(f"{len(reports)} report(s)")

    for _, report in reports.iterrows():
        report_id = int(report["id"])
        status_label = STATUS_LABELS.get(report["status"], report["status"])

        header = (
            f"{report['ref_number']}  |  {report['manufacturer']}  |  "
            f"{report['period_start']} to {report['period_end']}  |  "
            f"${float(report['grand_total']):.2f}  |  {status_label}"
        )

        with st.expander(header):
            detail_col, action_col = st.columns([2, 1])

            with detail_col:
                st.write(f"**Reference:** {report['ref_number']}")
                st.write(f"**Generated:** {report['generated_date']}")
                st.write(f"**Coupons:** {report['coupon_count']}")
                st.write(f"**Grand Total:** ${float(report['grand_total']):.2f}")
                st.write(f"**Status:** {status_label}")

                if report["sent_date"]:
                    st.write(f"**Sent:** {report['sent_date']}")
                if report["response_date"]:
                    st.write(f"**Response received:** {report['response_date']}")
                if report["payment_amount"] is not None:
                    st.write(f"**Payment amount:** ${float(report['payment_amount']):.2f}")
                if report["check_reference"]:
                    st.write(f"**Check / reference:** {report['check_reference']}")
                if report["notes"]:
                    st.write(f"**Notes:** {report['notes']}")

            with action_col:
                pdf_bytes = _build_pdf_from_snapshot(report_id, conn, settings)
                if pdf_bytes:
                    filename = (
                        f"coupon_report_{report['manufacturer'].replace(' ', '_')}"
                        f"_{report['generated_date']}.pdf"
                    )
                    st.download_button(
                        label="Download PDF",
                        data=pdf_bytes,
                        file_name=filename,
                        mime="application/pdf",
                        use_container_width=True,
                        key=f"dl_{report_id}",
                    )

                if report["status"] == "draft":
                    if st.button(
                        "Delete Draft",
                        key=f"delete_{report_id}",
                        type="secondary",
                        use_container_width=True,
                    ):
                        cursor = conn.cursor()
                        cursor.execute("DELETE FROM reports WHERE id = %s AND status = 'draft'", (report_id,))
                        conn.commit()
                        cursor.close()
                        st.success("Draft report deleted.")
                        st.rerun()

            st.divider()

            with st.form(f"report_status_{report_id}"):
                st.caption("Update status and response")

                new_status = st.selectbox(
                    "Status",
                    options=list(STATUS_LABELS.keys()),
                    format_func=lambda s: STATUS_LABELS[s],
                    index=list(STATUS_LABELS.keys()).index(report["status"]),
                    key=f"status_{report_id}",
                )

                fcol1, fcol2 = st.columns(2)
                with fcol1:
                    new_sent_date = st.date_input(
                        "Sent Date",
                        value=report["sent_date"] if report["sent_date"] else None,
                        key=f"sent_{report_id}",
                    )
                    new_payment = st.number_input(
                        "Payment Amount ($)",
                        value=float(report["payment_amount"]) if report["payment_amount"] is not None else 0.0,
                        min_value=0.0,
                        step=0.01,
                        format="%.2f",
                        key=f"payment_{report_id}",
                    )
                with fcol2:
                    new_response_date = st.date_input(
                        "Response Date",
                        value=report["response_date"] if report["response_date"] else None,
                        key=f"resp_{report_id}",
                    )
                    new_check_ref = st.text_input(
                        "Check / Reference Number",
                        value=report["check_reference"] or "",
                        key=f"check_{report_id}",
                    )

                new_notes = st.text_area(
                    "Notes",
                    value=report["notes"] or "",
                    key=f"notes_{report_id}",
                )

                if st.form_submit_button("Save", use_container_width=True, type="primary"):
                    cursor = conn.cursor()
                    cursor.execute(
                        """UPDATE reports
                           SET status          = %s,
                               sent_date       = %s,
                               response_date   = %s,
                               payment_amount  = %s,
                               check_reference = %s,
                               notes           = %s
                           WHERE id = %s""",
                        (
                            new_status,
                            new_sent_date if new_sent_date else None,
                            new_response_date if new_response_date else None,
                            round(new_payment, 2) if new_payment else None,
                            new_check_ref.strip() or None,
                            new_notes.strip() or None,
                            report_id,
                        ),
                    )
                    conn.commit()
                    cursor.close()
                    st.success("Report updated.")
                    st.rerun()

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
        ["Enter Coupons", "Generate Reports", "Report History", "Manage Manufacturers", "Settings"],
    )

    if st.sidebar.button("Sign out"):
        st.logout()

    if page == "Enter Coupons":
        page_enter_coupons()
    elif page == "Generate Reports":
        page_generate_reports()
    elif page == "Report History":
        page_report_history()
    elif page == "Manage Manufacturers":
        page_manage_manufacturers()
    elif page == "Settings":
        page_settings()


if __name__ == "__main__":
    main()