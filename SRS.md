# Software Requirements Specification (SRS)

## Verifiable Finance Copilot: SQL + RAG Agent with a Built-in Evaluation Framework

Version: 1.0
Status: Draft for phase-wise implementation
Project type: Academic / portfolio project (LLM agents, retrieval, evals, production backend)

---

## 1. Introduction

### 1.1 Purpose
This document specifies the requirements for a personal finance copilot that answers questions over both structured data (transactions, budgets, bills in PostgreSQL) and unstructured data (bank statements, loan agreements, insurance policies as PDFs). It is the single reference for building the system phase by phase.

### 1.2 Problem Statement
Standard RAG retrieves a handful of text chunks and asks an LLM to read them. This fails for questions that need aggregation or arithmetic (for example "total food spending last quarter"), because the model sees only a fraction of the data and computes numbers unreliably. This system routes numeric questions to SQL (exact answers) and policy or terms questions to document retrieval (cited answers), and combines both for mixed questions.

### 1.3 Core Pitch
"Every number is traced to a SQL result, every claim is cited to a document page, and a benchmark proves it."

### 1.4 Scope
In scope (core):
- Text-to-SQL over a financial database with a read-only safety layer
- RAG over uploaded financial PDFs with hybrid search and reranking
- A LangGraph agent that routes between SQL, documents, or both
- Structured JSON answers with citations (SQL and document)
- An evaluation framework that benchmarks every component
- An ingestion pipeline for new transactions and documents (the "changing index")
- Web UI, Docker packaging, cloud deployment

In scope (stretch, only after core is complete):
- Long-term memory of user preferences and goals
- Budget alerts and spending insights
- Ranked, personalised recommendations

Out of scope:
- Real bank integrations or real payment actions
- Real financial advice (the system must show a "not financial advice" disclaimer)
- Handling real customer data in the public demo (synthetic or redacted data only)

### 1.5 Definitions
| Term | Meaning |
|---|---|
| RAG | Retrieval-Augmented Generation |
| Hybrid search | Keyword (BM25 / full-text) combined with vector similarity |
| Reranker | A model that re-scores top retrieved chunks for relevance |
| Execution accuracy | Whether generated SQL returns the same result as the gold SQL |
| MRR | Mean Reciprocal Rank |
| Faithfulness | Whether the answer is supported by the retrieved sources |
| Gold set | Hand-labelled questions with known correct answers or sources |

---

## 2. Overall Description

### 2.1 Product Perspective
A standalone web application with a Python backend, PostgreSQL (with pgvector), a React or Streamlit frontend, and an evaluation harness that runs both locally and in CI.

### 2.2 User Classes
| User | Description |
|---|---|
| End user | Uploads documents, asks questions about finances, views summaries |
| Developer / evaluator | Runs the evaluation suite, inspects traces, compares configurations |

### 2.3 Operating Environment
- Backend: Python 3.11+, FastAPI
- Database: PostgreSQL 15+ with pgvector extension
- Frontend: React.js (Streamlit acceptable as a faster alternative)
- Containers: Docker and docker-compose
- Hosting: any free-tier cloud (Render, Railway, Fly.io, or similar)

### 2.4 Constraints
- Demo uses synthetic transactions and sample or redacted documents only.
- LLM provider must be swappable through a single configuration layer.
- LLM-written SQL must never have write access to the database.
- The LLM must not perform arithmetic itself; numbers come from SQL results.

### 2.5 Assumptions
- A hosted LLM API (or a capable local model) is available.
- Documents are text-based PDFs; scanned PDFs (OCR) are a stretch goal.
- Currency defaults to INR; multi-currency is out of scope.

---

## 3. System Architecture

### 3.1 High-Level Flow
```
User question
   -> FastAPI endpoint
   -> LangGraph agent (router)
        -> run_sql tool            (schema lookup, SQL generation, validation, execution)
        -> search_documents tool   (hybrid search, rerank, citations)
        -> or both
   -> Answer composer (structured JSON with numbers + citations)
   -> Response to UI
   -> Trace logged (for evals and debugging)
```

### 3.2 Components
1. **API layer (FastAPI):** auth-free for demo (simple session ID), endpoints for chat, upload, ingestion, summaries, and eval runs.
2. **Agent layer (LangGraph):** router node, SQL subgraph, document subgraph, composer node, retry and failure handling.
3. **SQL tool:** schema retrieval, SQL generation, validation, read-only execution, result formatting.
4. **Document tool:** PDF parsing, chunking, embedding, hybrid search, reranking, citation building.
5. **Ingestion pipeline:** handles new transactions and new documents, deduplicates, and re-embeds only what changed.
6. **Evaluation framework:** gold datasets, metric scripts, RAGAS integration, CI runner, results dashboard.
7. **Storage:** PostgreSQL for relational data, pgvector for embeddings, a table for traces and eval results.

### 3.3 Recommended Technology Stack
| Layer | Choice |
|---|---|
| Backend | Python, FastAPI, Pydantic |
| Agent framework | LangGraph |
| Database | PostgreSQL |
| Vector store | pgvector |
| Embeddings | Sentence Transformers (for example BGE or E5 family) |
| Reranker | Cross-encoder via Sentence Transformers |
| Keyword search | PostgreSQL full-text search (tsvector) or BM25 |
| PDF parsing | PyMuPDF |
| Evaluation | RAGAS plus custom scripts, pytest |
| Frontend | React.js or Streamlit |
| Packaging and deploy | Docker, docker-compose, cloud host |
| CI | GitHub Actions |

---

## 4. Data Requirements

### 4.1 Relational Schema (synthetic data)
```sql
CREATE TABLE users (
  user_id        SERIAL PRIMARY KEY,
  name           TEXT NOT NULL,
  created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE accounts (
  account_id     SERIAL PRIMARY KEY,
  user_id        INT REFERENCES users(user_id),
  account_type   TEXT CHECK (account_type IN ('savings','current','credit_card','loan')),
  bank_name      TEXT,
  opening_balance NUMERIC(14,2)
);

CREATE TABLE categories (
  category_id    SERIAL PRIMARY KEY,
  name           TEXT UNIQUE NOT NULL,       -- food, rent, transport, ...
  type           TEXT CHECK (type IN ('income','expense'))
);

CREATE TABLE transactions (
  txn_id         BIGSERIAL PRIMARY KEY,
  user_id        INT REFERENCES users(user_id),
  account_id     INT REFERENCES accounts(account_id),
  txn_date       DATE NOT NULL,
  amount         NUMERIC(14,2) NOT NULL,     -- positive number
  direction      TEXT CHECK (direction IN ('debit','credit')),
  category_id    INT REFERENCES categories(category_id),
  merchant       TEXT,
  description    TEXT,
  source_hash    TEXT UNIQUE                  -- for deduplication on ingestion
);

CREATE TABLE budgets (
  budget_id      SERIAL PRIMARY KEY,
  user_id        INT REFERENCES users(user_id),
  category_id    INT REFERENCES categories(category_id),
  month          DATE NOT NULL,               -- first day of month
  limit_amount   NUMERIC(14,2) NOT NULL,
  UNIQUE (user_id, category_id, month)
);

CREATE TABLE bills (
  bill_id        SERIAL PRIMARY KEY,
  user_id        INT REFERENCES users(user_id),
  name           TEXT,
  amount         NUMERIC(14,2),
  due_date       DATE,
  status         TEXT CHECK (status IN ('paid','pending','overdue'))
);

CREATE TABLE goals (                          -- used by stretch features
  goal_id        SERIAL PRIMARY KEY,
  user_id        INT REFERENCES users(user_id),
  description    TEXT,
  target_amount  NUMERIC(14,2),
  target_date    DATE
);
```

### 4.2 Document Storage Schema
```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
  doc_id         SERIAL PRIMARY KEY,
  user_id        INT REFERENCES users(user_id),
  filename       TEXT NOT NULL,
  doc_type       TEXT,                        -- statement, loan, insurance, other
  content_hash   TEXT UNIQUE,                 -- skip re-processing unchanged files
  uploaded_at    TIMESTAMPTZ DEFAULT now(),
  status         TEXT DEFAULT 'processed'
);

CREATE TABLE chunks (
  chunk_id       BIGSERIAL PRIMARY KEY,
  doc_id         INT REFERENCES documents(doc_id) ON DELETE CASCADE,
  page_number    INT,
  section_title  TEXT,
  text           TEXT NOT NULL,
  tsv            TSVECTOR,                    -- keyword search
  embedding      VECTOR(384),                 -- dimension depends on the chosen model
  chunk_hash     TEXT
);
CREATE INDEX ON chunks USING gin (tsv);
CREATE INDEX ON chunks USING hnsw (embedding vector_cosine_ops);
```

### 4.3 Observability and Evaluation Tables
```sql
CREATE TABLE traces (
  trace_id       UUID PRIMARY KEY,
  user_id        INT,
  question       TEXT,
  route          TEXT,                        -- sql | documents | both
  tool_calls     JSONB,                       -- ordered list of tool calls and results
  final_answer   JSONB,
  latency_ms     INT,
  created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE eval_cases (
  case_id        SERIAL PRIMARY KEY,
  suite          TEXT,                        -- sql | retrieval | routing | citation | e2e
  question       TEXT,
  expected       JSONB,                       -- gold SQL, gold pages, expected route, expected values
  source         TEXT DEFAULT 'manual'        -- manual | user_feedback
);

CREATE TABLE eval_runs (
  run_id         SERIAL PRIMARY KEY,
  config_name    TEXT,                        -- e.g. "vector_only", "hybrid_rerank"
  git_commit     TEXT,
  started_at     TIMESTAMPTZ DEFAULT now(),
  metrics        JSONB
);
```

### 4.4 Synthetic Data Requirements
- At least 3 synthetic user profiles with 12 months of transactions each (roughly 2,000 to 5,000 rows per user).
- Realistic merchants, recurring bills, salary credits, seasonal spikes, and a few deliberate anomalies (duplicate charge, unusually large expense) for insight and alert testing.
- At least 6 sample documents: 2 bank statements, 2 loan agreements, 2 insurance policies (public samples or self-written, with fake data).
- A data generator script (`scripts/generate_data.py`) with a fixed random seed so results are reproducible.

---

## 5. Functional Requirements

Priority: **M** = Must (core), **S** = Should, **C** = Could (stretch).

### 5.1 Structured Data Analysis (SQL Tool)
| ID | Requirement | Priority |
|---|---|---|
| FR-SQL-1 | The system shall convert a natural-language question into a SQL query over the finance schema. | M |
| FR-SQL-2 | The system shall retrieve relevant schema context (table and column descriptions, sample values) before generating SQL. | M |
| FR-SQL-3 | Before execution, the system shall validate that the query is a single SELECT statement, uses only allowed tables, and contains no DDL or DML keywords. | M |
| FR-SQL-4 | The system shall execute queries with a read-only database role, a statement timeout (for example 5 seconds), and a row limit. | M |
| FR-SQL-5 | The system shall automatically scope every query to the current user (row-level filter or parameter injection), never relying on the LLM to add it. | M |
| FR-SQL-6 | If a query fails or returns an unexpected empty result, the agent shall retry with the error message as feedback, up to N attempts (default 2). | M |
| FR-SQL-7 | The system shall return the executed query, row count, and result values for use in citations. | M |
| FR-SQL-8 | The system shall support analysis of spending by category, merchant, and time period; income versus expense; budget versus actual; and upcoming or overdue bills. | M |

### 5.2 Document Intelligence (RAG Tool)
| ID | Requirement | Priority |
|---|---|---|
| FR-DOC-1 | The user shall be able to upload PDF documents through the API and UI. | M |
| FR-DOC-2 | The system shall extract text with page numbers and detect section headings where possible (PyMuPDF). | M |
| FR-DOC-3 | The system shall split text into overlapping chunks that preserve page and section metadata. | M |
| FR-DOC-4 | The system shall compute embeddings and store them in pgvector, plus a full-text search vector. | M |
| FR-DOC-5 | The system shall perform hybrid retrieval (vector and keyword) and merge results (for example Reciprocal Rank Fusion). | M |
| FR-DOC-6 | The system shall rerank the merged top-K results with a cross-encoder and return the top-N. | M |
| FR-DOC-7 | The system shall skip re-processing files whose content hash is already stored. | M |
| FR-DOC-8 | Retrieval shall be restricted to the current user's documents. | M |
| FR-DOC-9 | The system shall support optional metadata filters (document type, date). | S |
| FR-DOC-10 | The system shall support OCR for scanned PDFs. | C |

### 5.3 Agent and Tool Calling
| ID | Requirement | Priority |
|---|---|---|
| FR-AGT-1 | The agent shall decide per question whether to call the SQL tool, the document tool, or both. | M |
| FR-AGT-2 | The agent shall support multi-step plans (for example read loan terms, then query SQL with those terms). | M |
| FR-AGT-3 | All tool inputs and outputs shall be validated against Pydantic schemas. | M |
| FR-AGT-4 | The agent shall enforce a maximum number of steps and a timeout to avoid loops. | M |
| FR-AGT-5 | The agent shall refuse or ask a clarifying question when the question is out of scope or ambiguous. | S |
| FR-AGT-6 | The agent shall say "not found in your documents" instead of guessing when retrieval confidence is low. | M |
| FR-AGT-7 | The agent shall keep short-term conversation context within a session. | M |

### 5.4 Answer Generation and Citations
| ID | Requirement | Priority |
|---|---|---|
| FR-ANS-1 | Every response shall be returned as structured JSON containing the answer text, a list of numbers with sources, and a list of citations. | M |
| FR-ANS-2 | Every numeric value in the answer shall come from a SQL result; the LLM shall not compute or invent figures. | M |
| FR-ANS-3 | SQL citations shall include the query, tables used, date range, and row count. | M |
| FR-ANS-4 | Document citations shall include document name, page number, section, and a short supporting snippet. | M |
| FR-ANS-5 | The system shall include a "not financial advice" disclaimer on recommendations. | M |
| FR-ANS-6 | The system shall run a post-generation check that every number in the answer appears in a tool result, and flag or regenerate if not. | S |

Example response format:
```json
{
  "answer": "You spent ₹18,420 on food last month. Your loan allows prepayment after 12 months with a 2% fee.",
  "numbers": [{"label": "food_spend_last_month", "value": 18420, "source": "sql", "query_id": "q_104"}],
  "citations": [
    {"type": "sql", "query_id": "q_104", "query": "SELECT SUM(amount) ...", "tables": ["transactions","categories"], "rows": 63},
    {"type": "document", "doc": "home_loan_agreement.pdf", "page": 7, "section": "Prepayment terms", "snippet": "..."}
  ],
  "confidence": "high",
  "disclaimer": "This is informational and not financial advice."
}
```

### 5.5 Ingestion Pipeline (Changing Index)
| ID | Requirement | Priority |
|---|---|---|
| FR-ING-1 | The system shall accept new transactions (CSV upload or generator endpoint) and insert them idempotently using `source_hash` for deduplication. | M |
| FR-ING-2 | The system shall accept new documents and embed only new or changed chunks. | M |
| FR-ING-3 | The system shall support deleting a document, including its chunks and embeddings. | M |
| FR-ING-4 | A scheduled job shall simulate daily arrival of new transactions and statements. | S |
| FR-ING-5 | The system shall log ingestion statistics (rows added, duplicates skipped, chunks embedded). | S |

### 5.6 Evaluation Framework
| ID | Requirement | Priority |
|---|---|---|
| FR-EVAL-1 | The repo shall contain a gold dataset of at least 60 SQL questions with gold queries and expected results. | M |
| FR-EVAL-2 | The repo shall contain at least 50 retrieval questions labelled with the correct document and page. | M |
| FR-EVAL-3 | The repo shall contain at least 30 routing cases labelled with the expected tool(s). | M |
| FR-EVAL-4 | The framework shall compute: SQL execution accuracy, numerical consistency rate, retrieval hit rate@k and MRR, citation accuracy, routing accuracy, and answer faithfulness and relevance (RAGAS plus an LLM-as-judge calibrated on human labels). | M |
| FR-EVAL-5 | The framework shall support named configurations (for example `vector_only`, `hybrid`, `hybrid_rerank`, `baseline_rag_only`) and produce a comparison table. | M |
| FR-EVAL-6 | A GitHub Actions workflow shall run a fast subset of evals on each pull request and fail if key metrics regress beyond a threshold. | S |
| FR-EVAL-7 | User thumbs-down and corrections shall be stored and convertible into new eval cases. | S |
| FR-EVAL-8 | An evaluation report (Markdown and a simple dashboard page) shall be generated per run. | S |
| FR-EVAL-9 | A baseline "normal RAG only" pipeline (no SQL tool) shall be evaluated on the same numeric questions to quantify the benefit of SQL routing. | M |

### 5.7 User Interface
| ID | Requirement | Priority |
|---|---|---|
| FR-UI-1 | A chat page with message history and rendered citations (expandable SQL and document snippets). | M |
| FR-UI-2 | A document upload and list page. | M |
| FR-UI-3 | A summary page showing spending by category, budget versus actual, and upcoming bills. | S |
| FR-UI-4 | A trace viewer showing which tools were called, with inputs and outputs (useful for demos and debugging). | S |
| FR-UI-5 | Thumbs up/down feedback on each answer. | S |
| FR-UI-6 | An evaluation results page showing config comparison charts. | S |

### 5.8 Stretch Features
| ID | Requirement | Priority |
|---|---|---|
| FR-MEM-1 | Persist user preferences and goals across sessions and use them in answers. | C |
| FR-MEM-2 | Allow viewing and deleting stored memories. | C |
| FR-ALR-1 | Generate budget alerts when spending crosses a threshold (for example 80% of budget). | C |
| FR-ALR-2 | Generate weekly or monthly insight summaries as structured JSON. | C |
| FR-REC-1 | Rank candidate savings suggestions (for example categories to cut) using spending patterns and goals, evaluated on a hand-labelled set. | C |

---

## 6. External Interfaces

### 6.1 REST API (FastAPI)
| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/chat` | Send a question, receive structured answer with citations |
| POST | `/documents` | Upload and ingest a PDF |
| GET | `/documents` | List documents |
| DELETE | `/documents/{doc_id}` | Remove a document and its chunks |
| POST | `/transactions/ingest` | Ingest new transactions (CSV or JSON) |
| GET | `/summary` | Spending and budget summary |
| GET | `/traces/{trace_id}` | Retrieve a trace |
| POST | `/feedback` | Submit thumbs up/down with optional correction |
| POST | `/eval/run` | Trigger an evaluation run (developer only) |
| GET | `/eval/runs` | List evaluation runs and metrics |
| GET | `/health` | Health check |

### 6.2 Tool Interfaces (agent-internal)
```python
class RunSQLInput(BaseModel):
    question: str

class RunSQLOutput(BaseModel):
    query_id: str
    sql: str
    tables: list[str]
    rows: list[dict]
    row_count: int
    error: str | None

class SearchDocsInput(BaseModel):
    query: str
    doc_type: str | None = None
    top_k: int = 20
    top_n: int = 5

class SearchDocsOutput(BaseModel):
    results: list[DocChunk]   # doc, page, section, text, score
    confidence: float
```

### 6.3 External Services
- LLM provider API (configurable)
- Embedding and reranker models run locally via Sentence Transformers
- Optional: object storage for uploaded PDFs

---

## 7. Non-Functional Requirements

### 7.1 Security and Privacy
- NFR-SEC-1: SQL execution uses a dedicated read-only role with access limited to allowed tables.
- NFR-SEC-2: Per-user scoping is enforced in code, not by the prompt.
- NFR-SEC-3: SQL validation blocks multiple statements, comments used for injection, and non-SELECT statements.
- NFR-SEC-4: Secrets (API keys, DB credentials) are loaded from environment variables, never committed.
- NFR-SEC-5: The public demo uses synthetic or redacted data only, and the README states this.
- NFR-SEC-6: Prompt-injection hygiene: text inside uploaded documents is treated as data, never as instructions to the agent.

### 7.2 Performance
- NFR-PERF-1: Median end-to-end latency under 8 seconds for a single-tool question and under 15 seconds for a mixed question (depends on LLM provider).
- NFR-PERF-2: Document retrieval (hybrid plus rerank) under 1.5 seconds for a corpus of 10,000 chunks.
- NFR-PERF-3: Ingesting a 30-page PDF in under 30 seconds.

### 7.3 Reliability
- NFR-REL-1: LLM and tool calls have timeouts and bounded retries with backoff.
- NFR-REL-2: Failures return a clear error message, never a fabricated answer.
- NFR-REL-3: Ingestion is idempotent; re-running it never creates duplicates.
- NFR-REL-4: Structured logging with a trace ID per request.

### 7.4 Correctness Targets (initial goals, adjust after the baseline run)
| Metric | Target |
|---|---|
| SQL execution accuracy | 85% or higher |
| Numerical consistency (answer numbers match tool results) | 98% or higher |
| Retrieval hit rate@5 (hybrid plus rerank) | 85% or higher |
| Citation accuracy (cited page contains the claim) | 90% or higher |
| Routing accuracy | 90% or higher |
| Improvement over "RAG only" on aggregation questions | At least 30 percentage points |

### 7.5 Maintainability
- NFR-MAINT-1: Modular code layout, type hints, and linting (ruff, black).
- NFR-MAINT-2: Unit tests for SQL validation, chunking, and metric functions.
- NFR-MAINT-3: A README with architecture diagram, setup steps, results table, and known limitations.

### 7.6 Portability
- NFR-PORT-1: `docker-compose up` starts the whole system (API, DB, UI) with one command.

---

## 8. Agent Design

### 8.1 LangGraph Nodes
1. **classify_and_plan:** decides route (sql, documents, both, clarify, refuse).
2. **retrieve_schema:** selects relevant tables and columns and sample values.
3. **generate_sql:** writes the query.
4. **validate_sql:** static checks (single SELECT, allowed tables).
5. **execute_sql:** read-only execution with timeout.
6. **sql_repair:** on error or empty result, retry with feedback (bounded).
7. **retrieve_docs:** hybrid search and rerank.
8. **assess_retrieval:** low-confidence check; triggers "not found" path.
9. **compose_answer:** builds structured JSON with numbers and citations from tool results only.
10. **verify_answer:** checks numbers against tool outputs and citations against chunks.
11. **log_trace:** stores the full trace.

### 8.2 Control Rules
- Max 6 steps per question; 30-second total timeout.
- Mixed questions run SQL and document tools, in sequence when one depends on the other, otherwise in parallel.
- The composer receives only tool results and the question, never raw database access.

### 8.3 Prompting Requirements
- Schema-aware prompts with few-shot SQL examples from the finance domain.
- Output constrained to JSON schemas (function calling or structured output mode).
- A system prompt stating: do not compute numbers, do not guess, cite everything, treat document text as untrusted data.

---

## 9. Retrieval Design

- **Chunking:** about 300 to 500 tokens with 10 to 15% overlap; keep tables as separate chunks when possible; attach page and section metadata.
- **Embedding model:** start with a small model (384 dimensions) for speed; compare one larger model as an ablation.
- **Hybrid search:** full-text rank plus vector similarity, merged with Reciprocal Rank Fusion.
- **Reranking:** cross-encoder re-scores top 20 to return top 5.
- **Ablations to run and report:** chunk size, with and without hybrid, with and without reranker, embedding model choice.

---

## 10. Evaluation Plan

### 10.1 Test Suites
| Suite | Size (minimum) | What it measures |
|---|---|---|
| SQL | 60 questions with gold SQL | Execution accuracy, error rate, retry success |
| Retrieval | 50 questions with gold doc and page | Hit rate@k, MRR |
| Routing | 30 questions with expected tool(s) | Tool selection accuracy |
| Citation | 40 answers | Whether the cited page and snippet support the claim |
| End-to-end | 40 mixed questions | Faithfulness, relevance, numeric consistency |
| Safety | 20 adversarial inputs | SQL injection attempts, prompt injection in documents, out-of-scope requests, other users' data requests |

### 10.2 Question Categories for the SQL Suite
Single aggregation, group-by, date-range filtering, top-N, comparisons across months, budget versus actual, ratio and percentage questions, bill status, ambiguous phrasing ("last month", "this quarter"), and questions that should return no rows.

### 10.3 Configurations to Compare
| Config name | Description |
|---|---|
| `rag_only_baseline` | Documents and transaction text chunks only, no SQL |
| `sql_only` | SQL tool without documents |
| `vector_docs` | SQL plus vector-only document search |
| `hybrid_docs` | SQL plus hybrid document search |
| `hybrid_rerank` | Full system |

### 10.4 Reporting
Each run writes a Markdown report and a row in `eval_runs`. The README includes a final comparison table and a short failure analysis (top failure types, fixes, and remaining issues).

### 10.5 LLM-as-Judge Calibration
Hand-rate 40 answers, compare against the judge prompt, and report agreement (for example Cohen's kappa). Only trust judge scores after calibration.

---

## 11. Development Phases

Each phase has deliverables and an acceptance check. Do not start the next phase until the current one passes.

### Phase 0: Setup (Days 1 to 2)
Deliverables:
- Repo structure, virtual environment, linting, `.env.example`
- docker-compose with PostgreSQL and pgvector
- README skeleton with the problem statement and architecture diagram

Acceptance: `docker-compose up` starts the database; a health endpoint returns OK.

Suggested layout:
```
finance-copilot/
  app/
    api/            # FastAPI routes
    agent/          # LangGraph graph, nodes, prompts
    tools/          # sql_tool.py, doc_tool.py
    ingestion/      # pdf parsing, chunking, embedding, transactions
    db/             # models, migrations, roles
    evals/          # datasets, metrics, runners, reports
  scripts/          # generate_data.py, seed.py
  tests/
  ui/
  docs/
  docker-compose.yml
  SRS.md
  README.md
```

### Phase 1: Data and Text-to-SQL Baseline (Week 1)
Deliverables:
- Schema migrations and the synthetic data generator (seeded)
- SQL tool with schema retrieval, validation, read-only role, timeout, and user scoping
- The SQL gold set (start with 30 questions, grow to 60)
- Eval script producing execution accuracy

Acceptance: validation blocks all unsafe queries in unit tests; baseline execution accuracy is recorded in the first results table.

### Phase 2: Document Pipeline and Retrieval (Week 2)
Deliverables:
- PDF upload, parsing, chunking, embedding, storage
- Vector-only, keyword-only, hybrid, and reranked retrieval
- Retrieval gold set (50 questions with pages)
- Eval script for hit rate and MRR across configurations

Acceptance: a table comparing vector, keyword, hybrid, and hybrid plus rerank on the same questions; citations return correct page numbers in manual spot checks.

### Phase 3: Agent and Structured Answers (Week 3)
Deliverables:
- LangGraph agent with routing, SQL repair loop, retrieval assessment, and composer
- Structured JSON answers with SQL and document citations
- Verification step (numbers and citations)
- Routing gold set and end-to-end suite; baseline `rag_only` comparison

Acceptance: routing accuracy measured; "RAG only" versus "SQL plus RAG" results on aggregation questions recorded; no answer contains a number absent from tool results in the test set.

### Phase 4: Ingestion, UI, and Feedback (Week 4)
Deliverables:
- Idempotent transaction and document ingestion plus a scheduled simulation job
- Chat UI with expandable citations, document page, summary page, trace viewer, feedback buttons
- Feedback to eval-case pipeline

Acceptance: re-running ingestion adds no duplicates; a new document becomes searchable within a minute; feedback creates a new eval case.

### Phase 5: Hardening, CI, and Deployment (Week 5)
Deliverables:
- Safety suite (injection and out-of-scope tests)
- Timeouts, retries, structured logging, error handling
- GitHub Actions running unit tests and a fast eval subset with regression thresholds
- Dockerized deployment on a cloud host with a live link
- Final README: architecture diagram, results tables, ablations, failure analysis, limitations, demo video

Acceptance: CI fails on an intentionally degraded config; live demo works from a fresh browser; the README results match the latest eval run.

### Phase 6: User Testing (Week 5 to 6, in parallel)
Deliverables:
- 15 to 20 classmates try the app with synthetic profiles
- Their questions are logged, reviewed, and added to the eval set
- A short note on what changed after feedback

Acceptance: documented before-and-after metrics from at least one improvement driven by user questions.

### Phase 7: Stretch (only if time remains)
Order of preference: long-term memory, budget alerts and insights, ranked recommendations with a small labelled eval set, OCR for scanned PDFs.

---

## 12. Testing Strategy

| Level | What to test |
|---|---|
| Unit | SQL validator, query scoping, chunker, hash dedup, metric functions, JSON schema validation |
| Integration | Ingestion to retrieval flow, agent with mocked LLM, API endpoints |
| Evaluation | Suites in Section 10 |
| Safety | Injection, cross-user access attempts, destructive SQL attempts, malicious document text |
| Manual | UI walkthrough and citation spot checks |

---

## 13. Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Scope creep from the full feature list | Unfinished project | Core first; stretch features only after Phase 5 |
| LLM generates wrong or unsafe SQL | Wrong numbers or data exposure | Validation, read-only role, user scoping in code, repair loop, eval coverage |
| Ambiguous time phrases ("last month") | Wrong date ranges | Inject the current date into the prompt and add dedicated test cases |
| Poor PDF parsing (tables, layouts) | Weak retrieval | Test on varied PDFs; keep tables as separate chunks; add OCR only if needed |
| LLM-judge unreliable | Misleading metrics | Calibrate on human labels; rely on deterministic checks where possible |
| API cost and rate limits | Slow or blocked development | Cache LLM calls in dev, use a smaller model for evals, set budgets |
| Real data in the demo | Privacy problem | Synthetic or redacted data only; state this in the README |
| Overfitting to the gold set | Inflated results | Keep a held-out test split; add new cases from user feedback |

---

## 14. Deliverables Checklist

- [ ] Source code with tests
- [ ] Synthetic data generator and seed scripts
- [ ] Gold datasets (SQL, retrieval, routing, citation, e2e, safety)
- [ ] Evaluation runner and reports
- [ ] Results table comparing all configurations
- [ ] Live deployed URL
- [ ] Docker setup (one command start)
- [ ] CI workflow with regression thresholds
- [ ] README with architecture diagram, results, ablations, failure analysis, limitations
- [ ] 2-minute demo video
- [ ] Short write-up of user-testing findings

---

## 15. Resume Description (template, fill in your real numbers)

"Built a finance copilot that routes questions between a text-to-SQL tool (read-only, validated) and a hybrid-search RAG pipeline (pgvector, cross-encoder reranking) using a LangGraph agent. Designed an evaluation framework covering SQL execution accuracy, numerical consistency, retrieval hit rate, citation accuracy, and routing. Improved aggregation-question accuracy from **X%** (RAG only) to **Y%** and hit rate@5 from **A** to **B** with hybrid search and reranking. Deployed with Docker and CI regression checks; refined using questions from **N** student testers."

---

## 16. Interview Preparation Notes

Be ready to explain:
1. Why normal RAG fails on aggregation and how SQL routing fixes it.
2. How you prevent unsafe or cross-user SQL.
3. Why hybrid search and reranking, and the ablation results behind each choice.
4. How you verify that numbers and citations in answers are grounded.
5. How the agent decides which tool to use and what happens when a tool fails.
6. How the index stays fresh without duplicates or full re-embedding.
7. How you calibrated the LLM judge and what failed in your evals.
8. What you would change to run this in production at scale.
