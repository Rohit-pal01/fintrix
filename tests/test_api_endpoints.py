"""Direct Endpoint Tests for FastAPI Application (Phase 4 Deliverables)."""
import pytest
from app.api.routes import (
    health, chat, list_documents, get_financial_summary, 
    ingest_transactions, submit_feedback,
    ChatRequest, IngestTransactionsRequest, FeedbackRequest, sync_retriever
)
from app.db.connection import init_db, SessionLocal

@pytest.fixture(scope="module", autouse=True)
def setup_db():
    init_db()
    sync_retriever()

def test_health_endpoint():
    res = health()
    assert res["status"] == "ok"
    assert "version" in res

def test_chat_sql_query():
    with SessionLocal() as db:
        res = chat(ChatRequest(question="How much did I spend on food last month?", user_id=1), db=db)
        assert res["route"] == "sql"
        assert "food" in res["final_answer"]["answer"].lower()
        assert len(res["final_answer"]["citations"]) >= 1
        assert res["is_verified"] is True

def test_chat_document_query():
    with SessionLocal() as db:
        res = chat(ChatRequest(question="What is the lock-in period before which prepayment is not allowed on home loan?", user_id=1), db=db)
        assert res["route"] == "documents"
        assert "lock-in" in res["final_answer"]["answer"].lower()
        assert len(res["final_answer"]["citations"]) >= 1

def test_chat_refuse_query():
    with SessionLocal() as db:
        res = chat(ChatRequest(question="DROP TABLE users; -- malicious attempt", user_id=1), db=db)
        assert res["route"] == "refuse"
        assert "cannot fulfill" in res["final_answer"]["answer"].lower()

def test_financial_summary_endpoint():
    with SessionLocal() as db:
        res = get_financial_summary(user_id=1, db=db)
        assert "category_spending" in res
        assert "budgets" in res
        assert "bills" in res

def test_documents_list_endpoint():
    with SessionLocal() as db:
        res = list_documents(user_id=1, db=db)
        assert "documents" in res
        assert len(res["documents"]) >= 1

def test_idempotent_transaction_ingestion():
    import uuid
    uid = uuid.uuid4().hex[:6]
    csv_sample = f"""txn_date,amount,direction,category,merchant,description
2026-11-22,450.00,debit,food,Swiggy,Dinner delivery {uid}
2026-11-22,450.00,debit,food,Swiggy,Dinner delivery {uid}
2026-11-23,1200.00,debit,groceries,Nature's Basket,Weekend grocery {uid}
"""
    with SessionLocal() as db:
        res1 = ingest_transactions(IngestTransactionsRequest(csv_data=csv_sample, user_id=1), db=db)
        assert res1["status"] == "success"
        assert res1["rows_inserted"] == 2
        assert res1["duplicates_skipped"] == 1

        # Second ingestion: Idempotency check -> 0 inserted, all 3 skipped!
        res2 = ingest_transactions(IngestTransactionsRequest(csv_data=csv_sample, user_id=1), db=db)
        assert res2["rows_inserted"] == 0
        assert res2["duplicates_skipped"] == 3

def test_feedback_to_eval_case_pipeline():
    with SessionLocal() as db:
        chat_res = chat(ChatRequest(question="What is my total spending on groceries last month?", user_id=1), db=db)
        trace_id = chat_res["trace_id"]

        fb_res = submit_feedback(FeedbackRequest(
            trace_id=trace_id,
            rating="down",
            correction="The answer should also highlight seasonal festive groceries."
        ), db=db)
        assert fb_res["message"] == "Feedback submitted successfully."
