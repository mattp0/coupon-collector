# Coupon Report Manager

A simple desktop app (runs in your browser) for logging coupons collected at your store and generating per-manufacturer PDF reports.

## Setup

### 1. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the app

```bash
cd coupon_app
streamlit run app.py
```

This will open the app automatically in your browser at `http://localhost:8501`.

## Usage

1. **Settings** — First, enter your company name and address. This appears on every PDF report.
2. **Manage Manufacturers** — Add manufacturers and their mailing addresses.
3. **Enter Coupons** — Log each coupon with its ID, face value, date, and whether it has a handling fee.
4. **Generate Reports** — Select a manufacturer and date range, preview the summary, then download a PDF.

## Files

| File | Purpose |
|---|---|
| `app.py` | Main Streamlit UI |
| `database.py` | SQLite schema and initialization |
| `pdf_generator.py` | PDF report generation (ReportLab) |
| `requirements.txt` | Python dependencies |
| `coupons.db` | Auto-created SQLite database (your data lives here) |

## Backing Up Your Data

Your data is stored in `coupons.db` (a single file in the `coupon_app` folder). Copy this file to back it up.
