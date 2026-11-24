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
