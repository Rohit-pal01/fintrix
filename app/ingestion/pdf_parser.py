"""PDF Document Parser using PyMuPDF (fitz) with Section Heading Detection."""
import os
import hashlib
import re
import zipfile
import xml.etree.ElementTree as ET
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

def extract_text_from_docx(docx_path: str) -> List[Dict[str, Any]]:
    """Extracts text from a Microsoft Word .docx file using standard library zipfile & XML."""
    pages_data = []
    paragraphs = []
    try:
        with zipfile.ZipFile(docx_path) as docx:
            xml_content = docx.read('word/document.xml')
            tree = ET.fromstring(xml_content)
            # Find all text elements in the word namespace
            for p in tree.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}p'):
                texts = [node.text for node in p.iter('{http://schemas.openxmlformats.org/wordprocessingml/2006/main}t') if node.text]
                if texts:
                    paragraphs.append("".join(texts))
    except Exception as e:
        paragraphs = [f"Failed to read docx structure: {e}"]

    # Split paragraphs into ~400-word logical pages
    full_text = "\n\n".join(paragraphs)
    words = full_text.split()
    page_size = 350
    page_num = 1
    for i in range(0, max(1, len(words)), page_size):
        chunk_text = " ".join(words[i:i + page_size])
        if chunk_text.strip():
            pages_data.append({
                "page_number": page_num,
                "section_title": f"Document Section {page_num}",
                "text": chunk_text
            })
            page_num += 1

    return pages_data if pages_data else [{"page_number": 1, "section_title": "General", "text": full_text}]

def extract_text_from_markdown(md_path: str) -> List[Dict[str, Any]]:
    """Extracts text from Markdown (.md) or Text (.txt) files preserving headers."""
    pages_data = []
    with open(md_path, "r", encoding="utf-8", errors="ignore") as f:
        content = f.read()

    # Split on markdown headers (# or ##) or divide into ~350 word pages
    sections = re.split(r'\n(?=#{1,3}\s+)', content)
    page_num = 1
    for sec in sections:
        sec_text = sec.strip()
        if not sec_text:
            continue
        # Extract title if present
        title_match = re.match(r'^(#{1,3})\s+(.+)$', sec_text, re.MULTILINE)
        section_title = title_match.group(2).strip() if title_match else f"Section {page_num}"

        pages_data.append({
            "page_number": page_num,
            "section_title": section_title,
            "text": sec_text
        })
        page_num += 1

    return pages_data if pages_data else [{"page_number": 1, "section_title": "General", "text": content}]

def extract_text_from_document(file_path: str) -> List[Dict[str, Any]]:
    """
    Universal multi-format document parser.
    Supports: .pdf, .docx, .md, .markdown, .txt
    """
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".pdf":
        return extract_text_from_pdf(file_path)
    elif ext == ".docx":
        return extract_text_from_docx(file_path)
    elif ext in (".md", ".markdown", ".txt"):
        return extract_text_from_markdown(file_path)
    else:
        # Fallback text extractor
        return extract_text_from_markdown(file_path)

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
                if max_font_size >= 12 or (line_str.isupper() and len(line_str) < 55):
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
    """
    Helper to generate compact, professional financial PDFs without unnecessary page breaks or blank space voids.
    Sections flow naturally on the page; new pages are created only when vertical space is exhausted.
    """
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    doc = fitz.open()

    def draw_page_header(p, is_first: bool):
        if is_first:
            # Elegant header banner
            p.draw_rect(fitz.Rect(40, 30, 555, 68), color=None, fill=(0.08, 0.16, 0.32))
            p.insert_text(fitz.Point(52, 54), title, fontsize=11.5, fontname="helv", color=(1, 1, 1))
            p.insert_text(fitz.Point(395, 54), "OFFICIAL FINANCIAL CONTRACT", fontsize=7.5, fontname="helv", color=(0.75, 0.85, 0.95))
            return 82
        else:
            # Running header on continuation pages
            p.draw_line(fitz.Point(40, 35), fitz.Point(555, 35), color=(0.75, 0.80, 0.85), width=0.8)
            p.insert_text(fitz.Point(40, 30), f"{title} (Continued)", fontsize=8.5, fontname="helv", color=(0.4, 0.45, 0.5))
            return 50

    page = doc.new_page(width=595, height=842)
    curr_y = draw_page_header(page, is_first=True)
    max_y = 785

    for sec in pages_content:
        sec_title = sec.get("section", title)
        sec_text = sec.get("text", "").strip()

        # Measure text height needed using a test off-screen canvas
        test_doc = fitz.open()
        test_page = test_doc.new_page(width=595, height=2000)
        unused = test_page.insert_textbox(fitz.Rect(40, 0, 555, 2000), sec_text, fontsize=9.2, fontname="helv")
        needed_body_height = 2000 - unused
        test_doc.close()

        total_sec_height = needed_body_height + 26  # title + divider + spacing

        # If it doesn't fit on the current page and we've already written text on it, advance to new page
        if curr_y + total_sec_height > max_y and curr_y > 100:
            page = doc.new_page(width=595, height=842)
            curr_y = draw_page_header(page, is_first=False)

        # Draw Section Heading
        page.insert_text(fitz.Point(40, curr_y + 10), sec_title, fontsize=10, fontname="helv", color=(0.1, 0.2, 0.45))
        page.draw_line(fitz.Point(40, curr_y + 14), fitz.Point(555, curr_y + 14), color=(0.85, 0.88, 0.92), width=0.6)
        curr_y += 20

        # Draw Section Body
        box_rect = fitz.Rect(40, curr_y, 555, max_y)
        unused = page.insert_textbox(box_rect, sec_text, fontsize=9.2, fontname="helv", color=(0.15, 0.15, 0.18))
        used = (max_y - curr_y) - unused
        curr_y += used + 14

    # Add professional running footers with total page numbers
    total_pages = len(doc)
    for idx, p in enumerate(doc):
        p.draw_line(fitz.Point(40, 800), fitz.Point(555, 800), color=(0.85, 0.85, 0.85), width=0.5)
        p.insert_text(
            fitz.Point(210, 815),
            f"Page {idx + 1} of {total_pages} - Confidential & Legally Binding Financial Record",
            fontsize=7.5,
            fontname="helv",
            color=(0.5, 0.55, 0.6)
        )

    doc.save(output_path)
    doc.close()
    return output_path
