"""Document Retrieval Engine with Hybrid Search (BM25 + Vector) & Reranking."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from rank_bm25 import BM25Okapi
from app.ingestion.embedder import get_text_embedding, cosine_similarity

class DocChunk(BaseModel):
    chunk_id: Optional[int] = None
    doc: str
    page: int
    section: str
    text: str
    score: float

class SearchDocsInput(BaseModel):
    query: str
    doc_type: Optional[str] = None
    top_k: int = 20
    top_n: int = 5
    mode: str = "hybrid_rerank"  # vector_only | keyword_only | hybrid | hybrid_rerank

class SearchDocsOutput(BaseModel):
    results: List[DocChunk]
    confidence: float
    mode_used: str

def reciprocal_rank_fusion(
    vector_ranks: List[Dict[str, Any]], 
    keyword_ranks: List[Dict[str, Any]], 
    k: int = 60
) -> List[Dict[str, Any]]:
    """
    RRF Formula: RRF_Score(d) = sum(1 / (k + rank_i))
    """
    scores = {}
    items = {}

    for rank, item in enumerate(vector_ranks):
        key = item.get("chunk_id", item["text"][:50])
        scores[key] = scores.get(key, 0.0) + (1.0 / (k + rank + 1))
        items[key] = item

    for rank, item in enumerate(keyword_ranks):
        key = item.get("chunk_id", item["text"][:50])
        scores[key] = scores.get(key, 0.0) + (1.0 / (k + rank + 1))
        items[key] = item

    sorted_keys = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    merged = []
    for key in sorted_keys:
        item = items[key].copy()
        item["rrf_score"] = scores[key]
        merged.append(item)

    return merged

def rerank_cross_encoder(query: str, candidates: List[Dict[str, Any]], top_n: int = 5) -> List[DocChunk]:
    """
    Cross-Encoder scoring simulation / model inference.
    Re-scores candidates based on fine-grained token match and semantic alignment.
    """
    q_words = set(query.lower().split())
    scored_candidates = []

    for item in candidates:
        text_lower = item["text"].lower()
        # Fine-grained overlap and proximity score
        overlap = sum(1 for w in q_words if w in text_lower)
        overlap_score = overlap / max(1, len(q_words))
        
        # Combined score with candidate baseline
        base_score = item.get("rrf_score", item.get("score", 0.5))
        final_score = round(0.4 * base_score + 0.6 * overlap_score, 4)

        scored_candidates.append(DocChunk(
            chunk_id=item.get("chunk_id"),
            doc=item.get("doc", "document.pdf"),
            page=item.get("page", 1),
            section=item.get("section", "General"),
            text=item.get("text", ""),
            score=final_score
        ))

    scored_candidates.sort(key=lambda x: x.score, reverse=True)
    return scored_candidates[:top_n]

class DocumentRetriever:
    """In-memory & DB-backed hybrid retriever."""
    def __init__(self, chunks: Optional[List[Dict[str, Any]]] = None):
        self.chunks = chunks or []
        self._init_bm25()

    def _init_bm25(self):
        if self.chunks:
            corpus = [c["text"].lower().split() for c in self.chunks]
            self.bm25 = BM25Okapi(corpus)
        else:
            self.bm25 = None

    def add_chunks(self, new_chunks: List[Dict[str, Any]]):
        self.chunks.extend(new_chunks)
        self._init_bm25()

    def search(
        self, 
        query: str, 
        top_k: int = 20, 
        top_n: int = 5, 
        mode: str = "hybrid_rerank",
        user_id: Optional[int] = None
    ) -> SearchDocsOutput:
        filtered_chunks = self.chunks
        if user_id is not None:
            system_docs = {
                "bank_statement_hdfc.pdf",
                "bank_statement_icici.pdf",
                "car_loan_agreement.pdf",
                "health_insurance_policy.pdf",
                "home_loan_agreement.pdf",
                "term_life_insurance.pdf"
            }
            filtered_chunks = [
                c for c in self.chunks 
                if c.get("user_id") == user_id or c.get("doc", "").lower() in system_docs
            ]

        if not filtered_chunks:
            return SearchDocsOutput(results=[], confidence=0.0, mode_used=mode)

        # 1. Vector Search
        q_emb = get_text_embedding(query)
        scored_vec = []
        for c in filtered_chunks:
            c_emb = c.get("embedding") or get_text_embedding(c["text"])
            sim = cosine_similarity(q_emb, c_emb)
            scored_vec.append({**c, "score": sim})
        scored_vec.sort(key=lambda x: x["score"], reverse=True)
        top_vec = scored_vec[:top_k]

        if mode == "vector_only":
            results = [
                DocChunk(
                    chunk_id=c.get("chunk_id"),
                    doc=c.get("doc", "document.pdf"),
                    page=c.get("page_number", c.get("page", 1)),
                    section=c.get("section_title", c.get("section", "General")),
                    text=c["text"],
                    score=round(c["score"], 4)
                ) for c in top_vec[:top_n]
            ]
            conf = results[0].score if results else 0.0
            return SearchDocsOutput(results=results, confidence=conf, mode_used=mode)

        # 2. Keyword Search (BM25)
        top_kw = []
        if self.bm25:
            tokens = query.lower().split()
            bm_scores = self.bm25.get_scores(tokens)
            indexed_scores = sorted(list(enumerate(bm_scores)), key=lambda x: x[1], reverse=True)
            for idx, s in indexed_scores[:top_k]:
                c = self.chunks[idx]
                top_kw.append({**c, "score": float(s)})

        if mode == "keyword_only":
            results = [
                DocChunk(
                    chunk_id=c.get("chunk_id"),
                    doc=c.get("doc", "document.pdf"),
                    page=c.get("page_number", c.get("page", 1)),
                    section=c.get("section_title", c.get("section", "General")),
                    text=c["text"],
                    score=round(c["score"], 4)
                ) for c in top_kw[:top_n]
            ]
            conf = min(1.0, results[0].score / 10.0) if results else 0.0
            return SearchDocsOutput(results=results, confidence=conf, mode_used=mode)

        # 3. Hybrid Search (RRF)
        merged = reciprocal_rank_fusion(top_vec, top_kw)

        if mode == "hybrid":
            results = [
                DocChunk(
                    chunk_id=c.get("chunk_id"),
                    doc=c.get("doc", "document.pdf"),
                    page=c.get("page_number", c.get("page", 1)),
                    section=c.get("section_title", c.get("section", "General")),
                    text=c["text"],
                    score=round(c.get("rrf_score", 0.5), 4)
                ) for c in merged[:top_n]
            ]
            conf = min(1.0, results[0].score * 30.0) if results else 0.0
            return SearchDocsOutput(results=results, confidence=conf, mode_used=mode)

        # 4. Hybrid + Reranking (Default)
        reranked = rerank_cross_encoder(query, merged[:top_k], top_n=top_n)
        conf = reranked[0].score if reranked else 0.0
        return SearchDocsOutput(results=reranked, confidence=conf, mode_used=mode)
