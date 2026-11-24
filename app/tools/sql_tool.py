"""Text-to-SQL Engine with Schema Retrieval, Generation, Safety, Execution, and Repair."""
import uuid
import re
from datetime import date, datetime
from typing import Dict, List, Any, Optional
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.llm import llm_client
from app.tools.validator import validate_sql, extract_tables, SQLValidationError
from app.db.models import Category, Account, Transaction

class RunSQLInput(BaseModel):
    question: str = Field(..., description="The natural language question to translate and execute via SQL.")
    user_id: Optional[int] = Field(None, description="Current authenticated user id for row scoping.")

class RunSQLOutput(BaseModel):
    query_id: str
    sql: str
    tables: List[str]
    rows: List[Dict[str, Any]]
    row_count: int
    error: Optional[str] = None

SCHEMA_DESCRIPTIONS = """
Database Schema (PostgreSQL/SQLite compatible):
- users (user_id INT PRIMARY KEY, name TEXT, created_at TIMESTAMP)
- accounts (account_id INT PRIMARY KEY, user_id INT, account_type TEXT, bank_name TEXT, opening_balance NUMERIC)
  * account_type values: 'savings', 'current', 'credit_card', 'loan'
- categories (category_id INT PRIMARY KEY, name TEXT UNIQUE, type TEXT)
  * name values: 'food', 'rent', 'utilities', 'transport', 'entertainment', 'shopping', 'healthcare', 'education', 'travel', 'groceries', 'insurance', 'investments', 'salary', 'freelance', 'dividends', 'cashback'
  * type values: 'income', 'expense'
- transactions (txn_id BIGINT PRIMARY KEY, user_id INT, account_id INT, txn_date DATE, amount NUMERIC, direction TEXT, category_id INT, merchant TEXT, description TEXT, source_hash TEXT)
  * direction values: 'debit' (money spent/outflow), 'credit' (money received/inflow)
  * amount is always positive NUMERIC(14,2)
- budgets (budget_id INT PRIMARY KEY, user_id INT, category_id INT, month DATE, limit_amount NUMERIC)
  * month is the 1st of the month (e.g. '2026-11-01')
- bills (bill_id INT PRIMARY KEY, user_id INT, name TEXT, amount NUMERIC, due_date DATE, status TEXT)
  * status values: 'paid', 'pending', 'overdue'
- goals (goal_id INT PRIMARY KEY, user_id INT, description TEXT, target_amount NUMERIC, target_date DATE)

CRITICAL RULES:
1. Always filter by user_id = {user_id}.
2. Use direction = 'debit' for expenses/spending and direction = 'credit' for income/earnings.
3. For monthly date filtering, reference CURRENT DATE: 2026-11-24.
   - Current month: txn_date >= '2026-11-01' AND txn_date <= '2026-11-30'
   - Last month (October 2026): txn_date >= '2026-10-01' AND txn_date <= '2026-10-31'
   - Last quarter (Q3 2026: Jul-Sep 2026): txn_date >= '2026-07-01' AND txn_date <= '2026-09-30'
   - Past 30 days: txn_date >= '2026-10-25' AND txn_date <= '2026-11-24'
4. Only return valid single SELECT queries. No comments, no writes.
"""

FEW_SHOT_EXAMPLES = [
    {
        "question": "How much did I spend on food last month?",
        "sql": "SELECT COALESCE(SUM(t.amount), 0) AS total_food_spending FROM transactions t JOIN categories c ON t.category_id = c.category_id WHERE t.user_id = {user_id} AND c.name = 'food' AND t.direction = 'debit' AND t.txn_date >= '2026-10-01' AND t.txn_date <= '2026-10-31';"
    },
    {
        "question": "What is my total spending by category this month?",
        "sql": "SELECT c.name AS category, COALESCE(SUM(t.amount), 0) AS total_spent FROM categories c LEFT JOIN transactions t ON c.category_id = t.category_id AND t.user_id = {user_id} AND t.direction = 'debit' AND t.txn_date >= '2026-11-01' AND t.txn_date <= '2026-11-30' WHERE c.type = 'expense' GROUP BY c.name ORDER BY total_spent DESC;"
    },
    {
        "question": "What are my top 5 merchants by spending over the last 3 months?",
        "sql": "SELECT t.merchant, COALESCE(SUM(t.amount), 0) AS total_spent FROM transactions t WHERE t.user_id = {user_id} AND t.direction = 'debit' AND t.txn_date >= '2026-08-25' AND t.txn_date <= '2026-11-24' AND t.merchant IS NOT NULL GROUP BY t.merchant ORDER BY total_spent DESC LIMIT 5;"
    },
    {
        "question": "What is my budget vs actual spending for food this month?",
        "sql": "SELECT b.limit_amount AS budget_limit, COALESCE(SUM(t.amount), 0) AS actual_spent, (b.limit_amount - COALESCE(SUM(t.amount), 0)) AS remaining_budget FROM budgets b JOIN categories c ON b.category_id = c.category_id LEFT JOIN transactions t ON t.category_id = c.category_id AND t.user_id = b.user_id AND t.direction = 'debit' AND t.txn_date >= '2026-11-01' AND t.txn_date <= '2026-11-30' WHERE b.user_id = {user_id} AND c.name = 'food' AND b.month = '2026-11-01' GROUP BY b.limit_amount;"
    },
    {
        "question": "Do I have any pending or overdue bills?",
        "sql": "SELECT bill_id, name, amount, due_date, status FROM bills WHERE user_id = {user_id} AND status IN ('pending', 'overdue') ORDER BY due_date ASC;"
    },
    {
        "question": "What was my total income vs total expenses over the last 6 months?",
        "sql": "SELECT t.direction, COALESCE(SUM(t.amount), 0) AS total_amount FROM transactions t WHERE t.user_id = {user_id} AND t.txn_date >= '2026-05-24' AND t.txn_date <= '2026-11-24' GROUP BY t.direction;"
    }
]

def retrieve_schema_context(db: Session, user_id: int) -> str:
    """Retrieve dynamic schema context with distinct user values for prompt grounding."""
    cats = db.query(Category.name).all()
    cat_names = [c[0] for c in cats] if cats else []

    accounts = db.query(Account.account_type, Account.bank_name).filter_by(user_id=user_id).all()
    acc_summary = [f"{a[0]} ({a[1]})" for a in accounts] if accounts else []

    return f"{SCHEMA_DESCRIPTIONS.format(user_id=user_id)}\nKnown Categories: {', '.join(cat_names)}\nUser Accounts: {', '.join(acc_summary)}"

def deterministic_text_to_sql(question: str, user_id: int) -> str:
    """
    Deterministic Text-to-SQL compiler for offline/eval/mock mode.
    Handles aggregations, category breakdowns, bills, budgets, and merchants.
    """
    q = question.lower()

    # Food spend last month
    if "food" in q and ("last month" in q or "previous month" in q or "october" in q):
        return (f"SELECT COALESCE(SUM(t.amount), 0) AS food_spend_last_month "
                f"FROM transactions t JOIN categories c ON t.category_id = c.category_id "
                f"WHERE t.user_id = {user_id} AND c.name = 'food' AND t.direction = 'debit' "
                f"AND t.txn_date >= '2026-10-01' AND t.txn_date <= '2026-10-31';")

    # Food spend this month
    if "food" in q and ("this month" in q or "current month" in q or "november" in q):
        return (f"SELECT COALESCE(SUM(t.amount), 0) AS food_spend_this_month "
                f"FROM transactions t JOIN categories c ON t.category_id = c.category_id "
                f"WHERE t.user_id = {user_id} AND c.name = 'food' AND t.direction = 'debit' "
                f"AND t.txn_date >= '2026-11-01' AND t.txn_date <= '2026-11-30';")

    # Groceries spend last month
    if "grocer" in q and ("last month" in q or "october" in q):
        return (f"SELECT COALESCE(SUM(t.amount), 0) AS groceries_spend_last_month "
                f"FROM transactions t JOIN categories c ON t.category_id = c.category_id "
                f"WHERE t.user_id = {user_id} AND c.name = 'groceries' AND t.direction = 'debit' "
                f"AND t.txn_date >= '2026-10-01' AND t.txn_date <= '2026-10-31';")

    # Spending by category this month
    if "category" in q and ("this month" in q or "november" in q or "current month" in q):
        return (f"SELECT c.name AS category, COALESCE(SUM(t.amount), 0) AS total_spent "
                f"FROM categories c LEFT JOIN transactions t ON c.category_id = t.category_id "
                f"AND t.user_id = {user_id} AND t.direction = 'debit' "
                f"AND t.txn_date >= '2026-11-01' AND t.txn_date <= '2026-11-30' "
                f"WHERE c.type = 'expense' GROUP BY c.name ORDER BY total_spent DESC;")

    # Spending by category last month
    if "category" in q and ("last month" in q or "october" in q):
        return (f"SELECT c.name AS category, COALESCE(SUM(t.amount), 0) AS total_spent "
                f"FROM categories c LEFT JOIN transactions t ON c.category_id = t.category_id "
                f"AND t.user_id = {user_id} AND t.direction = 'debit' "
                f"AND t.txn_date >= '2026-10-01' AND t.txn_date <= '2026-10-31' "
                f"WHERE c.type = 'expense' GROUP BY c.name ORDER BY total_spent DESC;")

    # Top merchants
    if "merchant" in q:
        limit_match = re.search(r'top\s+(\d+)', q)
        lim = int(limit_match.group(1)) if limit_match else 5
        return (f"SELECT t.merchant, COALESCE(SUM(t.amount), 0) AS total_spent "
                f"FROM transactions t WHERE t.user_id = {user_id} AND t.direction = 'debit' "
                f"AND t.merchant IS NOT NULL GROUP BY t.merchant ORDER BY total_spent DESC LIMIT {lim};")

    # Total spending / expenses this month
    if ("total spend" in q or "total expense" in q or "how much did i spend" in q) and "this month" in q:
        return (f"SELECT COALESCE(SUM(t.amount), 0) AS total_spent_this_month "
                f"FROM transactions t WHERE t.user_id = {user_id} AND t.direction = 'debit' "
                f"AND t.txn_date >= '2026-11-01' AND t.txn_date <= '2026-11-30';")

    # Total spending last month
    if ("total spend" in q or "total expense" in q or "how much did i spend" in q) and "last month" in q:
        return (f"SELECT COALESCE(SUM(t.amount), 0) AS total_spent_last_month "
                f"FROM transactions t WHERE t.user_id = {user_id} AND t.direction = 'debit' "
                f"AND t.txn_date >= '2026-10-01' AND t.txn_date <= '2026-10-31';")

    # Income vs expense
    if "income" in q and ("expense" in q or "spent" in q):
        return (f"SELECT t.direction, COALESCE(SUM(t.amount), 0) AS total_amount "
                f"FROM transactions t WHERE t.user_id = {user_id} GROUP BY t.direction;")

    # Total salary / income
    if "salary" in q or "income" in q:
        return (f"SELECT COALESCE(SUM(t.amount), 0) AS total_income "
                f"FROM transactions t WHERE t.user_id = {user_id} AND t.direction = 'credit';")

    # Budget vs actual
    if "budget" in q:
        cat_match = "food"
        for c in ["food", "groceries", "entertainment", "shopping"]:
            if c in q:
                cat_match = c
                break
        return (f"SELECT b.limit_amount AS budget_limit, COALESCE(SUM(t.amount), 0) AS actual_spent, "
                f"(b.limit_amount - COALESCE(SUM(t.amount), 0)) AS remaining_budget "
                f"FROM budgets b JOIN categories c ON b.category_id = c.category_id "
                f"LEFT JOIN transactions t ON t.category_id = c.category_id AND t.user_id = b.user_id "
                f"AND t.direction = 'debit' AND t.txn_date >= '2026-11-01' AND t.txn_date <= '2026-11-30' "
                f"WHERE b.user_id = {user_id} AND c.name = '{cat_match}' AND b.month = '2026-11-01' "
                f"GROUP BY b.limit_amount;")

    # Bills / upcoming / overdue
    if "bill" in q:
        if "overdue" in q:
            return f"SELECT bill_id, name, amount, due_date, status FROM bills WHERE user_id = {user_id} AND status = 'overdue' ORDER BY due_date ASC;"
        if "pending" in q:
            return f"SELECT bill_id, name, amount, due_date, status FROM bills WHERE user_id = {user_id} AND status = 'pending' ORDER BY due_date ASC;"
        return f"SELECT bill_id, name, amount, due_date, status FROM bills WHERE user_id = {user_id} ORDER BY due_date ASC;"

    # Goals
    if "goal" in q:
        return f"SELECT goal_id, description, target_amount, target_date FROM goals WHERE user_id = {user_id};"

    # Default fallback: recent transactions
    return (f"SELECT t.txn_id, t.txn_date, t.amount, t.direction, c.name AS category, t.merchant "
            f"FROM transactions t LEFT JOIN categories c ON t.category_id = c.category_id "
            f"WHERE t.user_id = {user_id} ORDER BY t.txn_date DESC LIMIT 10;")

def generate_sql(question: str, schema_context: str, user_id: int, feedback: Optional[str] = None) -> str:
    """Generate SQL from question using Live AI LLM (Gemini, OpenAI, Groq) or deterministic compiler."""
    if llm_client.is_live_ai_enabled():
        system_prompt = f"{schema_context}\n\nCRITICAL: Return ONLY the raw SQL query. Do not wrap in markdown quotes. Single SELECT statement only."
        prompt = f"Write a SQL query for user_id={user_id} to answer this question: '{question}'."
        if feedback:
            prompt += f"\nPrevious attempt failed with error: {feedback}. Please fix the SQL."

        ai_response = llm_client.complete(prompt, system_prompt=system_prompt)
        if ai_response:
            # Clean possible markdown ticks
            clean_sql = re.sub(r'```(?:sql)?', '', ai_response).strip()
            clean_sql = clean_sql.strip('`').strip()
            # If AI returned a valid query
            if clean_sql.upper().startswith("SELECT"):
                return clean_sql

    # Deterministic compiler fallback for offline mode, testing, or API failure
    sql = deterministic_text_to_sql(question, user_id)
    if feedback and "syntax error" in feedback.lower():
        sql = sql.replace(";;", ";")
    return sql

def execute_sql(db: Session, sql: str, user_id: int) -> RunSQLOutput:
    """
    Validate, execute SQL with timeout and row limit, and return structured output.
    """
    query_id = f"q_{uuid.uuid4().hex[:8]}"

    # 1. Validation
    is_valid, error_msg = validate_sql(sql, expected_user_id=user_id)
    if not is_valid:
        return RunSQLOutput(
            query_id=query_id,
            sql=sql,
            tables=list(extract_tables(sql)),
            rows=[],
            row_count=0,
            error=f"SQL Validation Error: {error_msg}"
        )

    tables = list(extract_tables(sql))

    # 2. Execution with safety row limit
    try:
        # Clean semicolon for wrapper if necessary
        exec_sql = sql.strip().rstrip(';')
        # Wrap query to enforce hard limit
        limited_sql = f"SELECT * FROM ({exec_sql}) AS q_sub LIMIT {settings.MAX_QUERY_ROWS};"
        
        result = db.execute(text(limited_sql))
        rows = [dict(row._mapping) for row in result]
        
        # Convert Decimals/Dates to JSON serializable objects
        formatted_rows = []
        for r in rows:
            formatted_row = {}
            for k, v in r.items():
                if hasattr(v, "isoformat"):
                    formatted_row[k] = v.isoformat()
                elif hasattr(v, "__float__"):
                    formatted_row[k] = float(v)
                else:
                    formatted_row[k] = v
            formatted_rows.append(formatted_row)

        return RunSQLOutput(
            query_id=query_id,
            sql=sql,
            tables=tables,
            rows=formatted_rows,
            row_count=len(formatted_rows),
            error=None
        )
    except Exception as e:
        return RunSQLOutput(
            query_id=query_id,
            sql=sql,
            tables=tables,
            rows=[],
            row_count=0,
            error=str(e)
        )

def run_sql_with_repair(db: Session, question: str, user_id: int, max_retries: int = settings.MAX_RETRY_ATTEMPTS) -> RunSQLOutput:
    """
    End-to-end SQL tool execution with bounded repair loop.
    """
    schema_ctx = retrieve_schema_context(db, user_id)
    sql = generate_sql(question, schema_ctx, user_id)
    output = execute_sql(db, sql, user_id)

    attempt = 0
    while output.error and attempt < max_retries:
        attempt += 1
        sql = generate_sql(question, schema_ctx, user_id, feedback=output.error)
        output = execute_sql(db, sql, user_id)

    return output
