"""Tests for Multi-Format Document Ingestion (PDF, Word DOCX, Markdown MD, Text TXT)."""
import os
import pytest
from app.ingestion.pdf_parser import extract_text_from_document
from app.ingestion.chunker import chunk_document
from app.tools.doc_tool import DocumentRetriever

def test_markdown_and_text_ingestion(tmp_path):
    # 1. Create sample markdown policy
    md_file = tmp_path / "company_travel_policy.md"
    md_file.write_text(
        "# CORPORATE TRAVEL POLICY\n\n"
        "## Flight Bookings\n"
        "All domestic flights under 4 hours must be booked in Economy class.\n\n"
        "## Daily Meal Per Diem\n"
        "Employees are entitled to a daily food allowance of ₹1,500 without receipts.\n\n"
        "## Hotel Nightly Cap\n"
        "Metro city hotel stays are capped at ₹4,500 per night inclusive of breakfast.",
        encoding="utf-8"
    )

    pages = extract_text_from_document(str(md_file))
    assert len(pages) >= 2
    assert "Daily Meal Per Diem" in [p["section_title"] for p in pages]

    chunks = chunk_document(pages)
    assert len(chunks) >= 2

    # Verify RAG can search and retrieve from this markdown document
    retriever = DocumentRetriever([
        {"chunk_id": idx, "doc": "company_travel_policy.md", "page": c["page_number"], "section": c["section_title"], "text": c["text"], "user_id": 1}
        for idx, c in enumerate(chunks)
    ])

    search_res = retriever.search("What is the daily meal per diem allowance?", mode="hybrid_rerank")
    assert len(search_res.results) > 0
    top = search_res.results[0]
    assert "1,500" in top.text
    assert top.doc == "company_travel_policy.md"
