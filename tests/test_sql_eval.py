"""SQL Benchmark Evaluation Test (Phase 1 Deliverable)."""
import pytest
from app.db.connection import SessionLocal
from app.evals.datasets import SQL_GOLD_SET
from app.evals.metrics import compute_sql_execution_accuracy

def test_sql_execution_benchmark():
    with SessionLocal() as db:
        metrics = compute_sql_execution_accuracy(db, SQL_GOLD_SET, user_id=1)
        print("\n=== Phase 1 SQL Execution Benchmark Results ===")
        print(f"Total Cases: {metrics['total_cases']}")
        print(f"Execution Accuracy: {metrics['execution_accuracy_pct']}% (Target: >= 85%)")
        print(f"Yield Rate: {metrics['yield_rate_pct']}%")
        if metrics['errors']:
            print(f"Errors encountered: {metrics['errors']}")

        assert metrics["total_cases"] == 60
        assert metrics["execution_accuracy_pct"] >= 85.0
