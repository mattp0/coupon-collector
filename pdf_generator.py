import io
from datetime import date

import pandas as pd
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

DARK_BLUE  = colors.HexColor("#1B3A5C")
MID_BLUE   = colors.HexColor("#2E6DA4")
LIGHT_GREY = colors.HexColor("#F4F6F9")
MID_GREY   = colors.HexColor("#D0D7E2")
TEXT_DARK  = colors.HexColor("#1A1A2E")
TEXT_MUTED = colors.HexColor("#5A6478")
WHITE      = colors.white
ACCENT     = colors.HexColor("#E8F0FB")


def generate_pdf(
    company_settings: dict,
    manufacturer: str,
    manufacturer_address: str,
    ref_number: str,
    start_date: date,
    end_date: date,
    coupons: pd.DataFrame,
) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.75 * inch,
        rightMargin=0.75 * inch,
        topMargin=0.75 * inch,
        bottomMargin=0.75 * inch,
    )

    story = []
    company_name    = company_settings.get("company_name", "Your Company")
    company_address = company_settings.get("company_address", "")

    # --- Header ---
    left_lines = [f"<b>{company_name}</b>"] + [
        line for line in company_address.split("\n") if line.strip()
    ]
    right_lines = [
        f"<b>Ref #:</b>  {ref_number}",
        f"<b>Date:</b>   {date.today().strftime('%B %d, %Y')}",
        f"<b>Period:</b> {start_date.strftime('%m/%d/%Y')} - {end_date.strftime('%m/%d/%Y')}",
    ]

    header_left_style = ParagraphStyle(
        "header_left", fontName="Helvetica", fontSize=9,
        leading=14, textColor=WHITE, alignment=TA_LEFT,
    )
    header_right_style = ParagraphStyle(
        "header_right", fontName="Helvetica", fontSize=9,
        leading=14, textColor=WHITE, alignment=TA_RIGHT,
    )

    left_para  = Paragraph("<br/>".join(left_lines),  header_left_style)
    right_para = Paragraph("<br/>".join(right_lines), header_right_style)

    header_table = Table([[left_para, right_para]], colWidths=["60%", "40%"])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), DARK_BLUE),
        ("TOPPADDING",    (0, 0), (-1, -1), 14),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 14),
        ("LEFTPADDING",   (0, 0), (0, -1),  16),
        ("RIGHTPADDING",  (-1, 0), (-1, -1), 16),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
    ]))

    story.append(header_table)
    story.append(Spacer(1, 18))

    # --- Manufacturer section ---
    story.append(Paragraph(
        f"Manufacturer: {manufacturer}",
        ParagraphStyle(
            "mfr_title", fontName="Helvetica-Bold", fontSize=13,
            textColor=DARK_BLUE, leading=18,
        ),
    ))

    if manufacturer_address.strip():
        story.append(Paragraph(
            manufacturer_address.replace("\n", "<br/>"),
            ParagraphStyle(
                "mfr_sub", fontName="Helvetica", fontSize=9,
                textColor=TEXT_MUTED, leading=13,
            ),
        ))

    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=1.5, color=MID_BLUE, spaceAfter=14))

    # --- Coupon table ---
    handling_fee_val = float(company_settings.get("handling_fee", "0.08"))

    col_header_style = ParagraphStyle(
        "col_hdr", fontName="Helvetica-Bold", fontSize=9,
        textColor=WHITE, alignment=TA_CENTER,
    )
    cell_left = ParagraphStyle(
        "cell_l", fontName="Helvetica", fontSize=9,
        textColor=TEXT_DARK, alignment=TA_LEFT,
    )
    cell_right = ParagraphStyle(
        "cell_r", fontName="Helvetica", fontSize=9,
        textColor=TEXT_DARK, alignment=TA_RIGHT,
    )

    table_data = [[
        Paragraph("#",            col_header_style),
        Paragraph("Coupon ID",    col_header_style),
        Paragraph("Date",         col_header_style),
        Paragraph("Face Value",   col_header_style),
        Paragraph("Handling Fee", col_header_style),
        Paragraph("Line Total",   col_header_style),
    ]]

    total_face     = 0.0
    total_handling = 0.0

    for i, (_, row) in enumerate(coupons.iterrows(), start=1):
        face   = float(row["amount"])
        h_fee  = handling_fee_val if row["handling_fee"] else 0.0
        line_t = face + h_fee
        total_face     += face
        total_handling += h_fee

        table_data.append([
            Paragraph(str(i),                              cell_right),
            Paragraph(str(row["coupon_id"]),               cell_left),
            Paragraph(str(row["collected_date"]),          cell_left),
            Paragraph(f"${face:.2f}",                      cell_right),
            Paragraph(f"${h_fee:.2f}" if h_fee else "-",  cell_right),
            Paragraph(f"${line_t:.2f}",                    cell_right),
        ])

    grand_total = total_face + total_handling

    subtotal_label = ParagraphStyle(
        "sub_label", fontName="Helvetica-Bold", fontSize=9,
        textColor=TEXT_DARK, alignment=TA_RIGHT,
    )
    subtotal_val = ParagraphStyle(
        "sub_val", fontName="Helvetica-Bold", fontSize=9,
        textColor=TEXT_DARK, alignment=TA_RIGHT,
    )
    grand_label = ParagraphStyle(
        "grand_label", fontName="Helvetica-Bold", fontSize=10,
        textColor=WHITE, alignment=TA_RIGHT,
    )
    grand_val = ParagraphStyle(
        "grand_val", fontName="Helvetica-Bold", fontSize=10,
        textColor=WHITE, alignment=TA_RIGHT,
    )

    table_data += [
        ["", "", "", Paragraph("Total Face Value:",      subtotal_label), "",
                     Paragraph(f"${total_face:.2f}",     subtotal_val)],
        ["", "", "", Paragraph("Total Handling Fees:",   subtotal_label), "",
                     Paragraph(f"${total_handling:.2f}", subtotal_val)],
        ["", "", "", Paragraph("Grand Total:",           grand_label), "",
                     Paragraph(f"${grand_total:.2f}",    grand_val)],
    ]

    n_rows   = len(table_data)
    n_totals = 3

    col_widths = [0.4 * inch, 1.6 * inch, 1.1 * inch, 1.1 * inch, 1.1 * inch, 1.1 * inch]
    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        # Header row
        ("BACKGROUND",    (0, 0), (-1, 0), MID_BLUE),
        ("TOPPADDING",    (0, 0), (-1, 0), 8),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("LEFTPADDING",   (0, 0), (-1, 0), 6),
        ("RIGHTPADDING",  (0, 0), (-1, 0), 6),
        # Data rows
        ("TOPPADDING",    (0, 1), (-1, n_rows - n_totals - 1), 6),
        ("BOTTOMPADDING", (0, 1), (-1, n_rows - n_totals - 1), 6),
        ("LEFTPADDING",   (0, 1), (-1, n_rows - n_totals - 1), 6),
        ("RIGHTPADDING",  (0, 1), (-1, n_rows - n_totals - 1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, n_rows - n_totals - 1), [WHITE, LIGHT_GREY]),
        ("GRID",          (0, 0), (-1, n_rows - n_totals - 1), 0.4, MID_GREY),
        # Subtotal rows
        ("BACKGROUND",    (0, n_rows - n_totals), (-1, n_rows - 2), ACCENT),
        ("TOPPADDING",    (0, n_rows - n_totals), (-1, n_rows - 2), 6),
        ("BOTTOMPADDING", (0, n_rows - n_totals), (-1, n_rows - 2), 6),
        ("LINEABOVE",     (0, n_rows - n_totals), (-1, n_rows - n_totals), 1, MID_BLUE),
        # Grand total row
        ("BACKGROUND",    (0, n_rows - 1), (-1, n_rows - 1), DARK_BLUE),
        ("TOPPADDING",    (0, n_rows - 1), (-1, n_rows - 1), 8),
        ("BOTTOMPADDING", (0, n_rows - 1), (-1, n_rows - 1), 8),
        # Span label and empty cells in total rows
        ("SPAN", (0, n_rows - 3), (3, n_rows - 3)),
        ("SPAN", (0, n_rows - 2), (3, n_rows - 2)),
        ("SPAN", (0, n_rows - 1), (3, n_rows - 1)),
    ]))

    story.append(t)
    story.append(Spacer(1, 20))

    # --- Footer ---
    story.append(HRFlowable(width="100%", thickness=0.5, color=MID_GREY, spaceBefore=4, spaceAfter=8))
    story.append(Paragraph(
        f"This report was generated on {date.today().strftime('%B %d, %Y')}. "
        f"Total of {len(coupons)} coupon(s) enclosed for {manufacturer}.",
        ParagraphStyle(
            "footer", fontName="Helvetica-Oblique", fontSize=8,
            textColor=TEXT_MUTED, alignment=TA_CENTER,
        ),
    ))

    doc.build(story)
    return buffer.getvalue()
