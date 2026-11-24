-- PostgreSQL Schema for Verifiable Finance Copilot
CREATE EXTENSION IF NOT EXISTS vector;

-- 1. Relational Schema
CREATE TABLE IF NOT EXISTS users (
  user_id        SERIAL PRIMARY KEY,
  name           TEXT NOT NULL,
  created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS accounts (
  account_id     SERIAL PRIMARY KEY,
  user_id        INT REFERENCES users(user_id) ON DELETE CASCADE,
  account_type   TEXT CHECK (account_type IN ('savings','current','credit_card','loan')),
  bank_name      TEXT,
  opening_balance NUMERIC(14,2)
);

CREATE TABLE IF NOT EXISTS categories (
  category_id    SERIAL PRIMARY KEY,
  name           TEXT UNIQUE NOT NULL,
  type           TEXT CHECK (type IN ('income','expense'))
);

CREATE TABLE IF NOT EXISTS transactions (
  txn_id         BIGSERIAL PRIMARY KEY,
  user_id        INT REFERENCES users(user_id) ON DELETE CASCADE,
  account_id     INT REFERENCES accounts(account_id) ON DELETE CASCADE,
  txn_date       DATE NOT NULL,
  amount         NUMERIC(14,2) NOT NULL,
  direction      TEXT CHECK (direction IN ('debit','credit')),
  category_id    INT REFERENCES categories(category_id),
  merchant       TEXT,
  description    TEXT,
  source_hash    TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS budgets (
  budget_id      SERIAL PRIMARY KEY,
  user_id        INT REFERENCES users(user_id) ON DELETE CASCADE,
  category_id    INT REFERENCES categories(category_id),
  month          DATE NOT NULL,
  limit_amount   NUMERIC(14,2) NOT NULL,
  UNIQUE (user_id, category_id, month)
);

CREATE TABLE IF NOT EXISTS bills (
  bill_id        SERIAL PRIMARY KEY,
  user_id        INT REFERENCES users(user_id) ON DELETE CASCADE,
  name           TEXT,
  amount         NUMERIC(14,2),
  due_date       DATE,
  status         TEXT CHECK (status IN ('paid','pending','overdue'))
);

CREATE TABLE IF NOT EXISTS goals (
  goal_id        SERIAL PRIMARY KEY,
  user_id        INT REFERENCES users(user_id) ON DELETE CASCADE,
  description    TEXT,
  target_amount  NUMERIC(14,2),
  target_date    DATE
);

-- 2. Document Storage Schema
CREATE TABLE IF NOT EXISTS documents (
  doc_id         SERIAL PRIMARY KEY,
  user_id        INT REFERENCES users(user_id) ON DELETE CASCADE,
  filename       TEXT NOT NULL,
  doc_type       TEXT,
  content_hash   TEXT UNIQUE,
  uploaded_at    TIMESTAMPTZ DEFAULT now(),
  status         TEXT DEFAULT 'processed'
);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id       BIGSERIAL PRIMARY KEY,
  doc_id         INT REFERENCES documents(doc_id) ON DELETE CASCADE,
  page_number    INT,
  section_title  TEXT,
  text           TEXT NOT NULL,
  tsv            TSVECTOR,
  embedding      VECTOR(384),
  chunk_hash     TEXT
);

CREATE INDEX IF NOT EXISTS idx_chunks_tsv ON chunks USING gin (tsv);
CREATE INDEX IF NOT EXISTS idx_chunks_embedding ON chunks USING hnsw (embedding vector_cosine_ops);
CREATE INDEX IF NOT EXISTS idx_transactions_user_date ON transactions (user_id, txn_date);

-- 3. Observability and Evaluation Tables
CREATE TABLE IF NOT EXISTS traces (
  trace_id       UUID PRIMARY KEY,
  user_id        INT,
  question       TEXT,
  route          TEXT,
  tool_calls     JSONB,
  final_answer   JSONB,
  latency_ms     INT,
  created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS eval_cases (
  case_id        SERIAL PRIMARY KEY,
  suite          TEXT,
  question       TEXT,
  expected       JSONB,
  source         TEXT DEFAULT 'manual'
);

CREATE TABLE IF NOT EXISTS eval_runs (
  run_id         SERIAL PRIMARY KEY,
  config_name    TEXT,
  git_commit     TEXT,
  started_at     TIMESTAMPTZ DEFAULT now(),
  metrics        JSONB
);

CREATE TABLE IF NOT EXISTS feedback (
  feedback_id    SERIAL PRIMARY KEY,
  trace_id       UUID REFERENCES traces(trace_id),
  rating         TEXT CHECK (rating IN ('up','down')),
  correction     TEXT,
  created_at     TIMESTAMPTZ DEFAULT now()
);
