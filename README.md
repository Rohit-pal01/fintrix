# Verifiable Finance Copilot: SQL + RAG Agent with a Built-in Evaluation Framework

> **"Every number is traced to a SQL result, every claim is cited to a document page, and a benchmark proves it."**

[![CI](https://github.com/your-org/finance-copilot/actions/workflows/ci.yml/badge.svg)](https://github.com/your-org/finance-copilot)
[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## 1. System Architecture

```
User Query
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI REST API Layer                    │
│       (/api/chat, /api/documents, /api/summary, etc.)       │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 LangGraph Router Node                       │
│    (Classifies intent: SQL, Documents, Both, Refuse)        │
└──────────────┬──────────────────────────────┬───────────────┘
               │                              │
               ▼                              ▼
┌──────────────────────────────┐ ┌──────────────────────────────┐
│       SQL Subgraph           │ │     Document RAG Subgraph    │
│  - Schema Retrieval          │ │  - PyMuPDF Page Extraction   │
│  - Text-to-SQL Generation    │ │  - 384d Dense Vector Search  │
│  - AST Static Safety Layer   │ │  - BM25 Full-Text Keyword    │
│  - Read-Only Execution Role  │ │  - Reciprocal Rank Fusion    │
│  - Row-Level Tenant Scoping  │ │  - Cross-Encoder Reranker    │
│  - Bounded Repair Loop       │ │  - Low Confidence Filter     │
└──────────────┬───────────────┘ └──────────────┬───────────────┘
               │                                │
               └───────────────┬────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                 Answer Composer & Verifier                  │
│  - Formats Structured JSON with SQL & PDF citations         │
│  - Post-generation grounding check (zero ungrounded numbers)│
│  - Observability Trace Logging                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Benchmark Evaluation Results

The built-in evaluation framework tests all system components against reproducible gold datasets (SRS Section 10).

### A. SQL Execution Accuracy (Phase 1 Benchmark - 60 Gold Questions)
| Metric | Target | Result | Status |
|---|---|---|---|
| **SQL Execution Accuracy** | &ge; 85.0% | **100.0%** | Passed |
| **Yield Rate (Non-empty results)** | &ge; 80.0% | **98.33%** | Passed |
| **Safety Block Rate (Unsafe DML/DDL)** | 100.0% | **100.0%** | Passed |

### B. Retrieval Ablation Comparison (Phase 2 Benchmark - 50 Gold Questions)
Ablation study comparing 4 distinct retrieval configurations:

| Configuration | Hit Rate@1 | Hit Rate@3 | Hit Rate@5 | MRR | Description |
|---|---|---|---|---|---|
| `vector_only` | 54.0% | 72.0% | 78.0% | 0.6257 | Dense semantic cosine similarity only |
| `keyword_only` | 90.0% | 96.0% | 98.0% | 0.9367 | BM25 token matching |
| `hybrid` | 72.0% | 94.0% | 98.0% | 0.7997 | Reciprocal Rank Fusion (RRF) |
| **`hybrid_rerank`** | **86.0%** | **96.0%** | **98.0%** | **0.9033** | **Production Hybrid + Cross-Encoder Reranker** |

### C. Agent Routing & Aggregation Benchmark (Phase 3)
| Evaluation Metric | Target | Result | Status |
|---|---|---|---|
| **Routing Accuracy (30 Cases)** | &ge; 90.0% | **100.0%** | Passed |
| **RAG-Only Baseline on Aggregations** | - | **0.0%** | Fails (partial chunks only) |
| **Verifiable SQL Copilot on Aggregations** | &ge; 85.0% | **100.0%** | Passed |
| **Improvement Delta** | &ge; +30.0% | **+100.0%** | Passed |
| **Numerical Consistency Rate** | &ge; 98.0% | **100.0%** | Zero hallucinated numbers |

### D. Safety & Adversarial Suite (Phase 5 - 20 Cases)
- **100.0% Block Rate** on SQL injection, destructive queries, cross-user tenant data requests, prompt injection in documents, and out-of-scope tasks.

---

## 3. Quickstart & Installation

### Option 1: Run Locally

```bash
# 1. Clone repository
git clone https://github.com/your-org/finance-copilot.git
cd finance-copilot

# 2. Create virtual environment and install dependencies
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 3. Seed synthetic data (3 users, 6,986 transactions, 6 financial PDFs)
python scripts/generate_data.py
python scripts/generate_sample_documents.py

# 4. Start the server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

Visit the interactive Web UI at **`http://localhost:8000`** and the API docs at **`http://localhost:8000/docs`**.

### Option 2: Docker & Docker Compose (One-Command Deployment)

```bash
docker-compose up --build
```
This launches:
- **`fintrix_db`**: PostgreSQL 16 with pgvector extension & read-only safety roles
- **`fintrix_backend`**: FastAPI backend with full UI dashboard on port 8000

---

## 4. Running the Evaluation Suites

Run all benchmarks with a single command:

```bash
# Run all unit, integration, and benchmark tests
pytest -v

# Run specific evaluation phases
pytest -s tests/test_sql_eval.py           # Phase 1: SQL 60-question benchmark
pytest -s tests/test_retrieval_eval.py     # Phase 2: Retrieval 4-config ablations
pytest -s tests/test_agent_and_routing.py  # Phase 3: Routing & Aggregation Delta
pytest -s tests/test_safety_suite.py       # Phase 5: Adversarial & Safety tests
```

---

## 5. Structured Response Example

```json
{
  "answer": "You spent ₹14,240.50 on food last month. According to home_loan_agreement.pdf (Page 4): \"The borrower may prepay the loan after a lock-in period of 12 months with a 0% penalty for floating rate loans.\"",
  "numbers": [
    {
      "label": "food_spend_last_month",
      "value": 14240.5,
      "source": "sql",
      "query_id": "q_4a7b12"
    }
  ],
  "citations": [
    {
      "type": "sql",
      "query_id": "q_4a7b12",
      "query": "SELECT SUM(t.amount) FROM transactions t WHERE ...",
      "tables": ["transactions", "categories"],
      "rows": 48
    },
    {
      "type": "document",
      "doc": "home_loan_agreement.pdf",
      "page": 4,
      "section": "4. PREPAYMENT AND FORECLOSURE CHARGES",
      "snippet": "The borrower may prepay the loan after a lock-in period of 12 months..."
    }
  ],
  "confidence": "high",
  "disclaimer": "This is informational and not financial advice."
}
```

---

## 6. Failure Analysis & Known Limitations

1. **OCR on Scanned Images**: Scanned image PDFs without text layers require Tesseract/OCR (identified as a stretch feature in SRS Phase 7).
2. **Ambiguous Dates**: Natural language phrases like "last month" rely on the fixed temporal anchor (`2026-11-24`), which is injected into the schema context to prevent drift.
3. **Multi-Currency**: Synthetic data currently standardizes on INR (₹); multi-currency conversion is planned for future releases.

---

## 7. License
MIT License. Built for verifiable, trustworthy financial AI applications.
