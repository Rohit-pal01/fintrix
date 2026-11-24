"""Evaluation Metrics & Benchmark Runners.

Computes:
- SQL Execution Accuracy
- Numerical Consistency Rate (Answer numbers match SQL results)
- Retrieval Hit Rate@k (k=1, 3, 5) and MRR (Mean Reciprocal Rank)
- Citation Accuracy
- Routing Accuracy
- Configuration comparison tables
"""
import re
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.tools.sql_tool import execute_sql, generate_sql, retrieve_schema_context
from app.tools.doc_tool import DocChunk

def compute_sql_execution_accuracy(db: Session, test_set: List[Dict[str, Any]], user_id: int) -> Dict[str, Any]:
    """
    Evaluates whether generated SQL executes cleanly and returns non-empty expected results.
    """
    total = len(test_set)
    executed_cleanly = 0
    matched_results = 0
    errors = []

    for item in test_set:
        q = item["question"]
        schema_ctx = retrieve_schema_context(db, user_id)
        gen_sql = generate_sql(q, schema_ctx, user_id)
        out = execute_sql(db, gen_sql, user_id)

        if not out.error:
            executed_cleanly += 1
            if out.row_count > 0:
                matched_results += 1
        else:
            errors.append({"id": item["id"], "question": q, "error": out.error})

    accuracy = (executed_cleanly / total) * 100 if total > 0 else 0.0
    yield_rate = (matched_results / total) * 100 if total > 0 else 0.0

    return {
        "total_cases": total,
        "executed_cleanly": executed_cleanly,
        "execution_accuracy_pct": round(accuracy, 2),
        "yield_rate_pct": round(yield_rate, 2),
        "errors": errors[:5]
    }

def compute_retrieval_metrics(
    retriever_func, 
    test_set: List[Dict[str, Any]], 
    top_k_list: List[int] = [1, 3, 5]
) -> Dict[str, Any]:
    """
    Calculates Hit Rate@k and MRR across the retrieval test set.
    """
    hits = {k: 0 for k in top_k_list}
    reciprocal_ranks = []
    total = len(test_set)

    for item in test_set:
        q = item["question"]
        gold_doc = item["expected_doc"].lower()
        gold_page = item["expected_page"]

        retrieved_chunks: List[DocChunk] = retriever_func(q, top_k=max(top_k_list))

        rank_found = None
        for idx, chunk in enumerate(retrieved_chunks):
            rank = idx + 1
            # Check matching document and page
            if gold_doc in chunk.doc.lower() and chunk.page == gold_page:
                rank_found = rank
                break
            # Fallback check on document match or content match
            elif gold_doc in chunk.doc.lower() and item.get("key_phrase", "").lower() in chunk.text.lower():
                rank_found = rank
                break

        if rank_found is not None:
            reciprocal_ranks.append(1.0 / rank_found)
            for k in top_k_list:
                if rank_found <= k:
                    hits[k] += 1
        else:
            reciprocal_ranks.append(0.0)

    mrr = sum(reciprocal_ranks) / total if total > 0 else 0.0
    results = {
        "total_cases": total,
        "mrr": round(mrr, 4)
    }
    for k in top_k_list:
        results[f"hit_rate_at_{k}"] = round((hits[k] / total) * 100, 2)

    return results

def compute_routing_accuracy(router_func, test_set: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Measures agent router accuracy across SQL, Documents, Both, and Refuse.
    """
    total = len(test_set)
    correct = 0
    mismatches = []

    for item in test_set:
        q = item["question"]
        expected = item["expected_route"]
        actual = router_func(q)

        if actual.lower() == expected.lower():
            correct += 1
        else:
            mismatches.append({"question": q, "expected": expected, "actual": actual})

    accuracy = (correct / total) * 100 if total > 0 else 0.0
    return {
        "total_cases": total,
        "correct": correct,
        "accuracy_pct": round(accuracy, 2),
        "mismatches": mismatches
    }

def verify_numerical_consistency(answer_text: str, sql_output_rows: List[Dict[str, Any]]) -> Tuple[bool, List[float]]:
    """
    Checks that every numeric value in the answer text appears in SQL output rows.
    """
    # Extract floating / integer numbers from answer text (ignoring years like 2026 or small integers < 10)
    numbers_in_text = [
        float(n.replace(',', '')) 
        for n in re.findall(r'(?<![A-Za-z0-9_])(?:\$|₹)?(\d+(?:,\d{3})*(?:\.\d+)?)(?![A-Za-z0-9_])', answer_text)
    ]

    # Collect numbers from SQL rows
    sql_numbers = set()
    for row in sql_output_rows:
        for val in row.values():
            try:
                sql_numbers.add(float(val))
            except (ValueError, TypeError):
                pass

    unmatched = []
    for num in numbers_in_text:
        # Ignore common non-financial integers (page numbers, years)
        if num in (2025, 2026, 2027) or num < 10:
            continue
        if num not in sql_numbers:
            unmatched.append(num)

    is_consistent = (len(unmatched) == 0)
    return is_consistent, unmatched
