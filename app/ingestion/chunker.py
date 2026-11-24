"""Chunking Engine with Overlapping Windows and Metadata Preservation."""
import hashlib
import re
from typing import List, Dict, Any

def compute_chunk_hash(text: str, page_number: int, section_title: str) -> str:
    raw = f"{page_number}:{section_title}:{text.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()

def chunk_document(
    pages: List[Dict[str, Any]], 
    chunk_size_words: int = 250, 
    overlap_words: int = 35
) -> List[Dict[str, Any]]:
    """
    Splits document pages into overlapping text chunks (300-500 tokens approx).
    Preserves page number, section title, and unique chunk hash.
    """
    chunks = []

    for p in pages:
        page_num = p["page_number"]
        section = p.get("section_title", "General")
        text = p["text"]

        # Word-level sliding window
        words = text.split()
        if not words:
            continue

        step = max(1, chunk_size_words - overlap_words)
        for i in range(0, len(words), step):
            chunk_words = words[i:i + chunk_size_words]
            chunk_text = " ".join(chunk_words)
            if len(chunk_text.strip()) < 30:  # Skip tiny fragments
                continue

            c_hash = compute_chunk_hash(chunk_text, page_num, section)
            chunks.append({
                "page_number": page_num,
                "section_title": section,
                "text": chunk_text,
                "chunk_hash": c_hash
            })

    return chunks
