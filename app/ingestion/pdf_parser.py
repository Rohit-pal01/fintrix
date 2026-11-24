"""PDF Document Parser using PyMuPDF (fitz) with Section Heading Detection."""
import os
import hashlib
from typing import List, Dict, Any, Optional
import fitz  # PyMuPDF

class ParsedPage:
    def __init__(self, page_number: int, text: str, sections: List[Dict[str, Any]]):
        self.page_number = page_number
        self.text = text
        self.sections = sections

def compute_content_hash(file_bytes: bytes) -> str:
    """Computes SHA-256 hash of file content for idempotent ingestion."""
    return hashlib.sha256(file_bytes).hexdigest()

def extract_text_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """
    Extracts text page-by-page from a PDF, detecting section headings via font size heuristics.
    Returns list of page dicts with page_number, text, and headings.
    """
    doc = fitz.open(pdf_path)
    pages_data = []

    for page_idx in range(len(doc)):
        page = doc[page_idx]
        blocks = page.get_text("dict").get("blocks", [])
        page_text = []
        current_section = "General"

        for b in blocks:
            if "lines" not in b:
                continue
            for line in b["lines"]:
                line_text = ""
                max_font_size = 0
                for span in line["spans"]:
                    line_text += span["text"]
                    if span["size"] > max_font_size:
                        max_font_size = span["size"]
                
                line_str = line_text.strip()
                if not line_str:
                    continue

                # Heuristic: Larger font sizes or uppercase patterns signify headings
                if max_font_size >= 13 or (line_str.isupper() and len(line_str) < 50):
                    current_section = line_str

                page_text.append(line_str)

        full_text = "\n".join(page_text)
        pages_data.append({
            "page_number": page_idx + 1,
            "section_title": current_section,
            "text": full_text
        })

    doc.close()
    return pages_data

def create_sample_pdf(output_path: str, title: str, pages_content: List[Dict[str, str]]) -> str:
    """Helper to generate well-formed sample test PDFs using PyMuPDF."""
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    doc = fitz.open()

    for p in pages_content:
        page = doc.new_page(width=595, height=842)  # A4 size
        rect = fitz.Rect(50, 50, 545, 792)
        content_text = f"{p.get('section', title)}\n\n{p['text']}"
        page.insert_textbox(rect, content_text, fontsize=11, fontname="helv")

    doc.save(output_path)
    doc.close()
    return output_path
