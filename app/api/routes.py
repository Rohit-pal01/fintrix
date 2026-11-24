"""FastAPI Endpoints for Verifiable Finance Copilot."""
import os
import shutil
import time
import hashlib
import uuid
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.db.connection import get_db, SessionLocal
from app.db.models import (
    User, Transaction, Category, Budget, Bill, Goal, Document, Chunk, 
    Trace, EvalRun, EvalCase, Feedback
)
from app.agent.graph import FinanceCopilotAgent
from app.tools.doc_tool import DocumentRetriever
from app.ingestion.pdf_parser import extract_text_from_document, compute_content_hash
from app.ingestion.chunker import chunk_document
from app.ingestion.embedder import get_text_embedding
from app.ingestion.transactions import ingest_transactions_csv
from app.evals.datasets import SQL_GOLD_SET, RETRIEVAL_GOLD_SET, ROUTING_GOLD_SET
from app.evals.metrics import (
    compute_sql_execution_accuracy, compute_retrieval_metrics, compute_routing_accuracy
)

router = APIRouter()

# Global Document Retriever instance synced with DB
retriever_instance = DocumentRetriever()

def sync_retriever():
    """Sync retriever in-memory cache with database chunks."""
    with SessionLocal() as db:
        chunks = db.query(Chunk, Document.filename, Document.user_id).join(Document, Chunk.doc_id == Document.doc_id).all()
        chunks_data = [
            {
                "chunk_id": c.chunk_id,
                "doc": fname,
                "page": c.page_number,
                "section": c.section_title,
                "text": c.text,
                "embedding": c.embedding,
                "user_id": uid
            }
            for c, fname, uid in chunks
        ]
        retriever_instance.chunks = chunks_data
        retriever_instance._init_bm25()

# Request/Response Schemas
class ChatRequest(BaseModel):
    question: str
    user_id: int = 1

class FeedbackRequest(BaseModel):
    trace_id: str
    rating: str  # up | down
    correction: Optional[str] = None

class IngestTransactionsRequest(BaseModel):
    csv_data: str
    user_id: int = 1

@router.get("/health")
def health():
    return {"status": "ok", "timestamp": time.time(), "version": "1.0.0"}

@router.post("/session/init")
def init_session(db: Session = Depends(get_db)):
    """Initializes an isolated guest session for a new visitor."""
    import uuid
    guest_name = f"Guest_{uuid.uuid4().hex[:6]}"
    user = User(name=guest_name)
    db.add(user)
    db.commit()
    db.refresh(user)
    return {"user_id": user.user_id, "name": user.name}

@router.post("/chat")
def chat(req: ChatRequest, db: Session = Depends(get_db)):
    """Primary copilot chat endpoint returning structured JSON with citations."""
    agent = FinanceCopilotAgent(retriever=retriever_instance)
    state = agent.run(question=req.question, user_id=req.user_id, db=db)
    return {
        "trace_id": state.trace_id,
        "route": state.route,
        "final_answer": state.final_answer,
        "is_verified": state.is_verified,
        "latency_ms": state.latency_ms
    }

@router.post("/documents")
async def upload_document(
    file: UploadFile = File(...), 
    doc_type: str = Form("statement"),
    user_id: int = Form(1),
    db: Session = Depends(get_db)
):
    """Uploads and ingests a PDF document idempotently per user."""
    content = await file.read()
    c_hash = hashlib.sha256(content + f":user_{user_id}".encode()).hexdigest()

    existing = db.query(Document).filter_by(content_hash=c_hash, user_id=user_id).first()
    if existing:
        return {"message": "Document already ingested for this session.", "doc_id": existing.doc_id, "status": "duplicate"}

    # Save to disk
    upload_dir = os.path.join("data", "documents")
    os.makedirs(upload_dir, exist_ok=True)
    pdf_path = os.path.join(upload_dir, f"{user_id}_{file.filename}")
    with open(pdf_path, "wb") as f:
        f.write(content)
        f.write(content)

    # Database Document Record
    doc = Document(
        user_id=user_id,
        filename=file.filename,
        doc_type=doc_type,
        content_hash=c_hash,
        status="processed"
    )
    db.add(doc)
    db.flush()

    # Extract and Chunk (Supports PDF, Word DOCX, Markdown MD, Text TXT)
    pages = extract_text_from_document(pdf_path)
    chunks = chunk_document(pages)

    for ch in chunks:
        emb = get_text_embedding(ch["text"])
        chunk_obj = Chunk(
            doc_id=doc.doc_id,
            page_number=ch["page_number"],
            section_title=ch["section_title"],
            text=ch["text"],
            tsv=ch["text"],
            embedding=emb,
            chunk_hash=ch["chunk_hash"]
        )
        db.add(chunk_obj)

    db.commit()

    # If the uploaded document is a PDF, also automatically extract any transaction tables directly into SQL
    sql_txns_inserted = 0
    if file.filename.lower().endswith(".pdf"):
        from app.ingestion.transactions import extract_and_ingest_pdf_transactions
        try:
            res_txns = extract_and_ingest_pdf_transactions(db, pdf_path, user_id=user_id)
            sql_txns_inserted = res_txns.get("transactions_inserted_to_sql", 0)
        except Exception as e:
            print(f"Warning: PDF transaction table scan error: {e}")

    sync_retriever()

    return {
        "message": "Document processed successfully.",
        "doc_id": doc.doc_id,
        "chunks_indexed": len(chunks),
        "transactions_extracted_to_sql": sql_txns_inserted
    }

SYSTEM_DOCS = {
    "bank_statement_hdfc.pdf",
    "bank_statement_icici.pdf",
    "car_loan_agreement.pdf",
    "health_insurance_policy.pdf",
    "home_loan_agreement.pdf",
    "term_life_insurance.pdf"
}

@router.get("/documents")
def list_documents(user_id: int = 1, db: Session = Depends(get_db)):
    """Lists all stored documents for user plus the shared baseline demo fixtures."""
    # 1. User's private documents
    user_docs = db.query(Document).filter_by(user_id=user_id).all()
    
    # 2. Shared baseline demo fixtures (seeded under user 1)
    system_docs = []
    if user_id != 1:
        system_docs = db.query(Document).filter(
            Document.user_id == 1,
            Document.filename.in_(SYSTEM_DOCS)
        ).all()

    all_docs = user_docs + system_docs
    results = []
    for d in all_docs:
        c_count = db.query(Chunk).filter_by(doc_id=d.doc_id).count()
        results.append({
            "doc_id": d.doc_id,
            "filename": d.filename,
            "doc_type": d.doc_type,
            "uploaded_at": d.uploaded_at.isoformat() if d.uploaded_at else None,
            "chunk_count": c_count,
            "is_system": d.filename.lower() in SYSTEM_DOCS
        })
    return {"documents": results, "active_user_id": user_id}

@router.delete("/documents/{doc_id}")
def delete_document(doc_id: int, user_id: int = 1, db: Session = Depends(get_db)):
    """Deletes a document along with all its chunks, protecting baseline demo files."""
    doc = db.query(Document).filter_by(doc_id=doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    if doc.filename.lower() in SYSTEM_DOCS:
        raise HTTPException(
            status_code=403, 
            detail="Default baseline system documents are protected and cannot be deleted."
        )

    db.delete(doc)
    db.commit()
    sync_retriever()
    return {"message": f"Document '{doc.filename}' deleted successfully."}

@router.post("/transactions/ingest")
def ingest_transactions(req: IngestTransactionsRequest, db: Session = Depends(get_db)):
    """Ingests new transactions from CSV with SHA-256 deduplication."""
    res = ingest_transactions_csv(db, req.csv_data, user_id=req.user_id)
    return {"status": "success", **res}

@router.get("/summary")
def get_financial_summary(user_id: int = 1, db: Session = Depends(get_db)):
    """Provides high-level financial dashboard statistics with dynamic user ledger support."""
    # Check if this user has transactions
    user_txns_count = db.query(Transaction).filter_by(user_id=user_id).count()

    if user_txns_count > 0:
        # 1. User has transactions! Calculate actual debits across all user transactions
        # Outer join on Category ensures debits without an explicit category are not dropped
        spending = db.query(
            func.coalesce(Category.name, "Transfers & Other").label("cat_name"), 
            func.coalesce(func.sum(Transaction.amount), 0).label("total")
        ).select_from(Transaction).outerjoin(
            Category, 
            Transaction.category_id == Category.category_id
        ).filter(
            Transaction.user_id == user_id,
            Transaction.direction == 'debit'
        ).group_by(func.coalesce(Category.name, "Transfers & Other")).all()

        category_summary = {s[0]: float(s[1]) for s in spending if float(s[1]) > 0}

        # If categories were uncategorized or only grouped as general, break down by top transactions
        if not category_summary:
            top_txns = db.query(Transaction.description, Transaction.amount).filter(
                Transaction.user_id == user_id,
                Transaction.direction == 'debit'
            ).order_by(Transaction.amount.desc()).limit(6).all()
            category_summary = {t[0][:20]: float(t[1]) for t in top_txns}

        # Budgets: Check if user has explicit budget targets configured in the database
        explicit_budgets = db.query(Budget, Category.name).join(
            Category, Budget.category_id == Category.category_id
        ).filter(Budget.user_id == user_id).all()

        budget_summary = []
        if explicit_budgets:
            for b, cat_name in explicit_budgets:
                spent = category_summary.get(cat_name, 0.0)
                limit = float(b.limit_amount)
                budget_summary.append({
                    "category": cat_name,
                    "limit": limit,
                    "spent": spent,
                    "remaining": max(0.0, limit - spent)
                })
        else:
            # When statement only contains expenses without pre-configured limits,
            # present clear category totals and auto-benchmarked targets
            for cat_name, spent in category_summary.items():
                limit = round(spent * 1.25, 2)
                budget_summary.append({
                    "category": cat_name,
                    "limit": limit,
                    "spent": spent,
                    "remaining": max(0.0, limit - spent)
                })

        # Bills
        bills = db.query(Bill).filter_by(user_id=user_id).all()
        bill_summary = [
            {
                "bill_id": b.bill_id,
                "name": b.name,
                "amount": float(b.amount),
                "due_date": b.due_date.isoformat(),
                "status": b.status
            }
            for b in bills
        ]

        return {
            "current_month": "Personal Statement Ledger",
            "is_demo": False,
            "category_spending": category_summary,
            "budgets": budget_summary,
            "bills": bill_summary
        }
    else:
        # Fall back to demo user 1 statistics for new visitors with 0 uploads
        if user_id != 1:
            demo_data = get_financial_summary(user_id=1, db=db)
            demo_data["is_demo"] = True
            return demo_data

        # Baseline demo data for user 1
        spending = db.query(
            Category.name, 
            func.coalesce(func.sum(Transaction.amount), 0).label("total")
        ).outerjoin(
            Transaction, 
            (Transaction.category_id == Category.category_id) & 
            (Transaction.user_id == 1) & 
            (Transaction.direction == 'debit') & 
            (Transaction.txn_date >= '2026-11-01')
        ).group_by(Category.name).all()

        category_summary = {s[0]: float(s[1]) for s in spending if float(s[1]) > 0}

        budgets = db.query(Budget, Category.name).join(Category, Budget.category_id == Category.category_id).filter(
            Budget.user_id == 1,
            Budget.month == '2026-11-01'
        ).all()

        budget_summary = []
        for b, cat_name in budgets:
            spent = category_summary.get(cat_name, 0.0)
            # Calibrate demo limits realistically so they display clean healthy bars rather than all 100% red overflow
            limit = float(b.limit_amount)
            if limit < spent:
                limit = round(spent * 1.25, 2)
            budget_summary.append({
                "category": cat_name,
                "limit": limit,
                "spent": spent,
                "remaining": max(0.0, limit - spent)
            })

        bills = db.query(Bill).filter_by(user_id=1).all()
        bill_summary = [
            {
                "bill_id": b.bill_id,
                "name": b.name,
                "amount": float(b.amount),
                "due_date": b.due_date.isoformat(),
                "status": b.status
            }
            for b in bills
        ]

        return {
            "current_month": "2026-11",
            "is_demo": True,
            "category_spending": category_summary,
            "budgets": budget_summary,
            "bills": bill_summary
        }

@router.get("/traces/{trace_id}")
def get_trace(trace_id: str, db: Session = Depends(get_db)):
    """Retrieves observability trace."""
    trace = db.query(Trace).filter_by(trace_id=trace_id).first()
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found.")
    return {
        "trace_id": trace.trace_id,
        "question": trace.question,
        "route": trace.route,
        "tool_calls": trace.tool_calls,
        "final_answer": trace.final_answer,
        "latency_ms": trace.latency_ms,
        "created_at": trace.created_at.isoformat() if trace.created_at else None
    }

@router.post("/feedback")
def submit_feedback(fb: FeedbackRequest, db: Session = Depends(get_db)):
    """Submits user feedback and automatically creates an evaluation case."""
    trace = db.query(Trace).filter_by(trace_id=fb.trace_id).first()
    if not trace:
        raise HTTPException(status_code=404, detail="Trace not found.")

    feedback_record = Feedback(
        trace_id=fb.trace_id,
        rating=fb.rating,
        correction=fb.correction
    )
    db.add(feedback_record)

    # Convert negative feedback into an evaluation case (FR-EVAL-7)
    if fb.rating == "down" and fb.correction:
        eval_case = EvalCase(
            suite="user_feedback",
            question=trace.question,
            expected={"correction": fb.correction, "previous_trace": fb.trace_id},
            source="user_feedback"
        )
        db.add(eval_case)

    db.commit()
    return {"message": "Feedback submitted successfully."}

@router.post("/eval/run")
def trigger_eval_run(config_name: str = "hybrid_rerank", db: Session = Depends(get_db)):
    """Triggers complete benchmark evaluation across SQL, Retrieval, and Routing."""
    sql_metrics = compute_sql_execution_accuracy(db, SQL_GOLD_SET, user_id=1)

    def retriever_fn(q, top_k):
        return retriever_instance.search(q, top_k=top_k, top_n=top_k, mode=config_name, user_id=1).results

    retrieval_metrics = compute_retrieval_metrics(retriever_fn, RETRIEVAL_GOLD_SET, top_k_list=[1, 3, 5])

    def router_fn(q):
        agent = FinanceCopilotAgent(retriever_instance)
        st = agent.run(q, user_id=1, db=db)
        return st.route

    routing_metrics = compute_routing_accuracy(router_fn, ROUTING_GOLD_SET)

    all_metrics = {
        "sql": sql_metrics,
        "retrieval": retrieval_metrics,
        "routing": routing_metrics
    }

    run_record = EvalRun(
        config_name=config_name,
        metrics=all_metrics
    )
    db.add(run_record)
    db.commit()

    return {"run_id": run_record.run_id, "config_name": config_name, "metrics": all_metrics}

@router.get("/eval/runs")
def list_eval_runs(db: Session = Depends(get_db)):
    """Lists past evaluation runs."""
    runs = db.query(EvalRun).order_by(EvalRun.started_at.desc()).limit(20).all()
    return [
        {
            "run_id": r.run_id,
            "config_name": r.config_name,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "metrics": r.metrics
        }
        for r in runs
    ]
