"""Unit tests for PDF Bank Statement Table Extraction to SQL Pipeline."""
import os
import pytest
import fitz
from datetime import date
from sqlalchemy.orm import Session
from app.db.connection import SessionLocal
from app.db.models import Transaction, Account, Category
from app.ingestion.transactions import extract_and_ingest_pdf_transactions
from app.tools.sql_tool import execute_sql

@pytest.fixture
def sample_statement_pdf(tmp_path):
    """Generates a realistic bank statement PDF with a transaction table."""
    pdf_path = str(tmp_path / "test_sbi_statement.pdf")
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)

    # Header
    page.draw_rect(fitz.Rect(40, 30, 555, 75), color=None, fill=(0.08, 0.16, 0.32))
    page.insert_text(fitz.Point(52, 52), "STATE BANK OF INDIA - ACCOUNT STATEMENT", fontsize=11, fontname="helv", color=(1, 1, 1))
    page.insert_text(fitz.Point(52, 66), "Account No: 30918290192 | IFSC: SBIN0001042", fontsize=7.5, fontname="helv", color=(0.8, 0.85, 0.95))

    # Transaction Table
    table_data = [
        ["Txn Date", "Narration / Description", "Debit", "Credit", "Balance"],
        ["2026-10-02", "UPI/Swiggy Food Order", "650.00", "", "49,350.00"],
        ["2026-10-05", "Salary Credit Infosys Corp", "", "85,000.00", "1,34,350.00"],
        ["2026-10-12", "Blinkit Groceries Online", "1,350.00", "", "1,33,000.00"],
        ["2026-10-20", "Uber Ride Bangalore", "420.00", "", "1,32,580.00"]
    ]

    x0, y0 = 40, 100
    col_widths = [75, 195, 80, 80, 85]
    row_height = 24
    y = y0

    for r_idx, row in enumerate(table_data):
        x = x0
        for c_idx, cell in enumerate(row):
            rect = fitz.Rect(x, y, x + col_widths[c_idx], y + row_height)
            page.draw_rect(rect, color=(0.75, 0.75, 0.8), fill=(0.92, 0.94, 0.98) if r_idx == 0 else (1, 1, 1))
            page.insert_text(fitz.Point(x + 5, y + 16), cell, fontsize=8.5, fontname="helv", color=(0.1, 0.1, 0.1))
            x += col_widths[c_idx]
        y += row_height

    doc.save(pdf_path)
    doc.close()
    return pdf_path

def test_pdf_statement_table_extraction_to_sql(sample_statement_pdf):
    """
    Validates that:
    1. PyMuPDF extracts rows from the PDF statement table.
    2. Rows are inserted into the SQL transactions database.
    3. Exact SQL mathematical aggregation (SELECT SUM) returns 100% accurate results.
    """
    user_id = 999  # Isolated test user

    with SessionLocal() as db:
        # Ensure account exists for test user
        acc = db.query(Account).filter_by(user_id=user_id).first()
        if not acc:
            acc = Account(user_id=user_id, account_type="savings", bank_name="SBI", opening_balance=50000.0)
            db.add(acc)
            db.commit()

        # Clean existing transactions for test user
        db.query(Transaction).filter_by(user_id=user_id).delete()
        db.commit()

        # Ingest from PDF
        res = extract_and_ingest_pdf_transactions(db, sample_statement_pdf, user_id=user_id)
        assert res["transactions_inserted_to_sql"] == 4
        assert res["duplicates_skipped"] == 0

        # Run SQL exact calculation
        sql_query = f"SELECT SUM(amount) AS total_debit FROM transactions WHERE user_id = {user_id} AND direction = 'debit';"
        out = execute_sql(db, sql_query, user_id=user_id)
        assert not out.error
        assert out.row_count == 1

        # Expected debits: 650.00 + 1350.00 + 420.00 = 2420.00
        total_debit = out.rows[0]["total_debit"]
        assert total_debit == 2420.00

        # Expected credits: 85000.00
        sql_credit = f"SELECT SUM(amount) AS total_credit FROM transactions WHERE user_id = {user_id} AND direction = 'credit';"
        out_credit = execute_sql(db, sql_credit, user_id=user_id)
        assert not out_credit.error
        assert out_credit.rows[0]["total_credit"] == 85000.00

        # Clean up test user records
        db.query(Transaction).filter_by(user_id=user_id).delete()
        db.delete(acc)
        db.commit()
