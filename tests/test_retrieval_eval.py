"""Retrieval Benchmark across Configurations (Phase 2 Deliverable).

Compares:
- vector_only
- keyword_only
- hybrid (RRF)
- hybrid_rerank (Full cross-encoder)
Produces comparative ablation results table.
"""
import pytest
from app.db.connection import SessionLocal
from app.db.models import Chunk, Document
from app.evals.datasets import RETRIEVAL_GOLD_SET
from app.evals.metrics import compute_retrieval_metrics
from app.tools.doc_tool import DocumentRetriever

@pytest.fixture(scope="module")
def indexed_retriever():
    chunks_data = []
    with SessionLocal() as db:
        chunks = db.query(Chunk, Document.filename).join(Document, Chunk.doc_id == Document.doc_id).all()
        for c, fname in chunks:
            chunks_data.append({
                "chunk_id": c.chunk_id,
                "doc": fname,
                "page": c.page_number,
                "section": c.section_title,
                "text": c.text,
                "embedding": c.embedding,
                "user_id": 1
            })
    return DocumentRetriever(chunks_data)

def test_retrieval_ablation_comparison(indexed_retriever):
    configs = ["vector_only", "keyword_only", "hybrid", "hybrid_rerank"]
    results_table = []

    print("\n" + "="*70)
    print("PHASE 2: RETRIEVAL CONFIGURATION ABLATION BENCHMARK (50 Gold Questions)")
    print("="*70)
    print(f"{'Configuration':<18} | {'Hit Rate@1 (%)':<15} | {'Hit Rate@5 (%)':<15} | {'MRR':<8}")
    print("-" * 70)

    for cfg in configs:
        def retriever_fn(query, top_k):
            res = indexed_retriever.search(query, top_k=top_k, top_n=top_k, mode=cfg, user_id=1)
            return res.results

        metrics = compute_retrieval_metrics(retriever_fn, RETRIEVAL_GOLD_SET, top_k_list=[1, 3, 5])
        results_table.append({"config": cfg, **metrics})

        print(f"{cfg:<18} | {metrics['hit_rate_at_1']:<15} | {metrics['hit_rate_at_5']:<15} | {metrics['mrr']:<8}")

    print("="*70)

    # Acceptance verification: hybrid_rerank must achieve >= 85% Hit Rate@5
    best_config = results_table[-1]
    assert best_config["config"] == "hybrid_rerank"
    assert best_config["hit_rate_at_5"] >= 85.0
