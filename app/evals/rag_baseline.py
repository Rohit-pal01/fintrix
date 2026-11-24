"""Baseline RAG-Only Pipeline without Text-to-SQL.

Simulates a traditional RAG system that searches transaction text chunks 
and tries to estimate aggregations via top retrieved chunks. Demonstrates 
why RAG fails on arithmetic/aggregation and quantifies the improvement from SQL routing.
"""
from typing import List, Dict, Any
from app.tools.doc_tool import DocumentRetriever

class RagOnlyBaseline:
    def __init__(self, transaction_chunks: List[Dict[str, Any]]):
        self.retriever = DocumentRetriever(transaction_chunks)

    def answer_numeric_question(self, question: str, top_k: int = 5) -> Dict[str, Any]:
        """
        Traditional RAG: retrieves top-k chunks and tries to sum them.
        Since it only sees a fraction of the full dataset (e.g. 5 out of 60 transactions),
        it reliably produces incorrect or incomplete sums.
        """
        search_res = self.retriever.search(question, top_k=top_k, top_n=top_k, mode="vector_only")
        chunks = search_res.results

        # Sum whatever numbers happen to be in the top retrieved chunks
        partial_sum = 0.0
        for c in chunks:
            # Extract basic amount from text
            words = c.text.split()
            for w in words:
                try:
                    clean_w = w.replace('₹', '').replace(',', '').replace(';', '')
                    val = float(clean_w)
                    if 10.0 <= val <= 100000.0:
                        partial_sum += val
                        break
                except ValueError:
                    continue

        return {
            "answer": f"Based on retrieved chunks, total spending appears to be ₹{partial_sum:,.2f}.",
            "retrieved_chunk_count": len(chunks),
            "estimated_sum": round(partial_sum, 2)
        }
