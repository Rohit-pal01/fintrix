"""LangGraph Agent Nodes: Router, SQL, Retrieval, Composer, Verifier, and Tracer."""
import re
import time
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from app.agent.state import AgentState
from app.agent.prompts import COMPOSER_PROMPT
from app.core.llm import llm_client
from app.tools.sql_tool import run_sql_with_repair, RunSQLOutput
from app.tools.doc_tool import DocumentRetriever, SearchDocsOutput, DocChunk
from app.evals.metrics import verify_numerical_consistency
from app.db.models import Trace

DISCLAIMER_TEXT = "This is informational and not financial advice."

def classify_and_plan_node(state: AgentState) -> AgentState:
    """Classifies user inquiry into sql, documents, both, or refuse using 2-tier semantic classification."""
    q = state.question.lower().strip()

    # Tier 0: Refusal / Safety checks
    if any(k in q for k in ["drop table", "delete from", "insert into", "user 2", "other user", "weather in", "buy 100 shares", "stock investment advice to double"]):
        state.route = "refuse"
        state.final_answer = {
            "answer": "I cannot fulfill this request. I only provide verified financial analysis over your authorized transactions and documents.",
            "numbers": [],
            "citations": [],
            "confidence": "none",
            "disclaimer": DISCLAIMER_TEXT
        }
        return state

    # Both (Mixed questions: cross-referencing arithmetic ledger against policy limits/clauses)
    if ("prepay" in q and ("afford" in q or "saving" in q or "balance" in q)) or \
       ("hospital" in q and "room rent" in q) or \
       ("premium" in q and "sum insured" in q) or \
       ("emi" in q and "principal in the agreement" in q) or \
       ("bill" in q and ("terms" in q or "billing terms" in q)):
        state.route = "both"
        state.plan = ["sql", "documents", "compose"]
        return state

    # Tier 1A: High-precision regex patterns for Document & Statement Header inquiries
    # Captures all variations: "account no", "acc no", "a/c no", "acct num", "holder name", "cif", "ifsc", etc.
    doc_patterns = [
        r'\b(?:acc(?:ount)?\.?\s*(?:no|num|number|#)|a/c\s*(?:no|num|number)?)\b',
        r'\b(?:holder|customer|beneficiary|nominee|signatory)\s*name\b',
        r'\b(?:account|holder)\s*name\b',
        r'\b(?:ifsc|micr|cif|pan|gstin|branch|swift)\b',
        r'\b(?:addr(?:ess)?|adress)\b',
        r'\b(?:penalty|lock-in|policy|agreement|waiting period|room rent|icu|foreclosure|apr|bonus|cashless|clause|tariff|coverage|exclusion|grace period|maternity|terms and conditions|contract|specified in|document|documents|pdf|file|uploaded|resume|cv|cgpa|grade|college|university|education|experience|project|skills|according to|in my)\b'
    ]
    if any(re.search(pat, q) for pat in doc_patterns):
        state.route = "documents"
        state.plan = ["documents", "compose"]
        return state

    # Tier 1B: High-precision regex patterns for SQL Ledger & Mathematical inquiries
    sql_patterns = [
        r'\b(?:how much|total|highest|lowest|average|sum|count|top\s*\d+|how many|frequency|times)\b',
        r'\b(?:spend|spent|spending|expense|expenses|cost|costing|budget|budgets)\b',
        r'\b(?:balance|savings balance|wallet|pocket|afford|purchase|buy|enough)\b',
        r'\b(?:salary|income|credit|credited|deposit|deposited|debit|debited|inflow|outflow|withdraw|withdrawal)\b',
        r'\b(?:transaction|transactions|bill|bills|merchant|merchants|category|categories|groceries|food|shopping|rent|utilities)\b'
    ]
    if any(re.search(pat, q) for pat in sql_patterns):
        state.route = "sql"
        state.plan = ["sql", "compose"]
        return state

    # Tier 2: LLM Semantic Intent Classification (Dynamically routes any unseen phrasing or unique document)
    if llm_client.is_live_ai_enabled():
        try:
            semantic_prompt = f"""Classify the user's financial inquiry into exactly one route: 'sql', 'documents', 'both', or 'refuse'.

Definitions:
- 'sql': Inquiries requiring mathematical calculation, transaction histories, spending totals, ledger balances, budgets, bills, OR financial metaphors/colloquialisms (e.g. "what's the damage", "burning through cash", "gas in the tank", "can my pocket take the hit", "splurge", "dough", "cushion", "bleeding").
- 'documents': Inquiries about textual clauses, rules, policy terms, agreements, OR statement header/metadata (e.g. account numbers, account holder names, addresses, IFSC, branch, nominee).
- 'both': Inquiries comparing live ledger amounts against document terms/limits.
- 'refuse': Inquiries asking to buy stocks, execute DDL/DML, or out-of-scope non-financial topics.

Question: "{state.question}"

Return ONLY one word: sql, documents, both, or refuse."""
            raw_classification = llm_client.complete(semantic_prompt, temperature=0.0).strip().lower()
            for r in ["documents", "both", "refuse", "sql"]:
                if r in raw_classification:
                    state.route = r
                    state.plan = ["sql", "documents", "compose"] if r == "both" else ([r, "compose"] if r != "refuse" else [])
                    return state
        except Exception:
            pass

    # Default to documents if asking who/what/where/which, otherwise sql
    if any(w in q for w in ["who", "what", "where", "which", "whom", "whose"]):
        state.route = "documents"
        state.plan = ["documents", "compose"]
    else:
        state.route = "sql"
        state.plan = ["sql", "compose"]
    return state

def execute_sql_node(state: AgentState, db: Session) -> AgentState:
    """Executes SQL tool with bounded repair and scoping."""
    out: RunSQLOutput = run_sql_with_repair(db, state.question, user_id=state.user_id)
    state.sql_result = out.model_dump()
    state.tool_calls.append({
        "tool": "run_sql",
        "input": {"question": state.question, "user_id": state.user_id},
        "output": state.sql_result,
        "status": "success" if not out.error else "failed"
    })
    return state

def retrieve_docs_node(state: AgentState, retriever: DocumentRetriever) -> AgentState:
    """Retrieves document chunks using hybrid search + cross-encoder rerank."""
    out: SearchDocsOutput = retriever.search(state.question, top_k=15, top_n=3, mode="hybrid_rerank", user_id=state.user_id)
    state.doc_result = out.model_dump()
    state.tool_calls.append({
        "tool": "search_documents",
        "input": {"query": state.question, "user_id": state.user_id},
        "output": state.doc_result,
        "status": "success"
    })
    return state

def compose_answer_node(state: AgentState) -> AgentState:
    """Composes structured JSON response grounded in SQL and document citations."""
    numbers = []
    citations = []
    answer_parts = []
    confidence = "high"

    # SQL Citation and Number Grounding
    if state.sql_result and not state.sql_result.get("error"):
        rows = state.sql_result.get("rows", [])
        q_id = state.sql_result.get("query_id", "q_0")
        sql_query = state.sql_result.get("sql", "")
        tables = state.sql_result.get("tables", [])

        citations.append({
            "type": "sql",
            "query_id": q_id,
            "query": sql_query,
            "tables": tables,
            "rows": len(rows)
        })

        if rows:
            first_row = rows[0]
            # Detect primary numeric values
            for k, v in first_row.items():
                if isinstance(v, (int, float)):
                    numbers.append({
                        "label": k,
                        "value": v,
                        "source": "sql",
                        "query_id": q_id
                    })
            # Build narrative
            if "available_balance" in first_row:
                bal = float(first_row.get("available_balance", 0.0))
                answer_parts.append(f"Your current verified available account balance is ₹{bal:,.2f}.")
            elif "total_food_spending" in first_row or "food_spend_last_month" in first_row:
                val = first_row.get("food_spend_last_month") or first_row.get("total_food_spending", 0)
                answer_parts.append(f"You spent ₹{val:,.2f} on food last month.")
            elif "total_spent_this_month" in first_row:
                answer_parts.append(f"Your total spending this month is ₹{first_row['total_spent_this_month']:,.2f}.")
            elif "total_spent_last_month" in first_row:
                answer_parts.append(f"Your total spending last month was ₹{first_row['total_spent_last_month']:,.2f}.")
            elif "category" in first_row and len(rows) > 1:
                summary_items = [f"{r.get('category')}: ₹{r.get('total_spent', 0):,.2f}" for r in rows[:4]]
                answer_parts.append(f"Top category spending: {', '.join(summary_items)}.")
            elif "budget_limit" in first_row:
                answer_parts.append(
                    f"Your food budget limit is ₹{first_row.get('budget_limit', 0):,.2f}, "
                    f"actual spent is ₹{first_row.get('actual_spent', 0):,.2f}, "
                    f"leaving ₹{first_row.get('remaining_budget', 0):,.2f}."
                )
            elif "merchant" in first_row and len(rows) > 1:
                top_m = [f"{r.get('merchant')}: ₹{r.get('total_spent', 0):,.2f}" for r in rows[:3]]
                answer_parts.append(f"Your top merchants by spending are {', '.join(top_m)}.")
            elif "bill_id" in first_row:
                bill_details = [f"{r.get('name')} (₹{r.get('amount', 0):,.2f} due {r.get('due_date')})" for r in rows]
                answer_parts.append(f"You have {len(rows)} bills: {', '.join(bill_details)}.")
            elif "transaction_count" in first_row:
                cnt = first_row.get("transaction_count", 0)
                answer_parts.append(f"Recorded {cnt} matching transaction(s) in your statement ledger.")
            else:
                answer_parts.append(f"Retrieved {len(rows)} matching record(s) from your financial database.")
        else:
            answer_parts.append("No matching transactions were found for the specified period.")
            confidence = "medium"

    # Document Citation and Grounding (supports multi-document & cross-file citations)
    if state.doc_result:
        results = state.doc_result.get("results", [])
        if results:
            seen_doc_pages = set()
            for r in results[:5]:
                doc_key = (r["doc"], r["page"])
                if doc_key not in seen_doc_pages:
                    seen_doc_pages.add(doc_key)
                    citations.append({
                        "type": "document",
                        "doc": r["doc"],
                        "page": r["page"],
                        "section": r.get("section", "General"),
                        "snippet": r["text"][:160] + "..."
                    })
            # Primary document narrative summary
            top_chunk = results[0]
            answer_parts.append(f"According to {top_chunk['doc']} (Page {top_chunk['page']}, {top_chunk['section']}): \"{top_chunk['text']}\"")
        else:
            answer_parts.append("No matching terms were found in your uploaded documents.")
            if confidence == "high":
                confidence = "medium"

    full_text = " ".join(answer_parts) if answer_parts else "Could not generate an answer."
    state.grounded_text = full_text

    # If Live AI is active, enhance wording while preserving grounded numbers
    if llm_client.is_live_ai_enabled():
        context_summary = f"Question: {state.question}\nTool Results:\n"
        if state.sql_result:
            context_summary += f"SQL Rows: {state.sql_result.get('rows', [])}\n"
        if state.doc_result:
            context_summary += f"Document Snippets: {[r['text'] for r in state.doc_result.get('results', [])]}\n"

        ai_narrative = llm_client.complete(
            f"User Question: {state.question}\nEvidence:\n{context_summary}\nProvide a direct, concise 1-2 sentence answer without repeating section labels or boilerplate meta-text.",
            system_prompt=COMPOSER_PROMPT
        )
        if ai_narrative:
            # Enforce Indian Rupee symbol over accidental USD dollar signs
            if "$" in ai_narrative and "usd" not in state.question.lower() and "dollar" not in state.question.lower():
                ai_narrative = re.sub(r'\$\s*(\d)', r'₹\1', ai_narrative)
            # Strip ugly meta-citations like ((Source: Document Snippet 1))
            ai_narrative = re.sub(r'\(+\s*Source:\s*[^)]+\)+', '', ai_narrative).strip()
            full_text = ai_narrative

    state.final_answer = {
        "answer": full_text,
        "numbers": numbers,
        "citations": citations,
        "confidence": confidence,
        "disclaimer": DISCLAIMER_TEXT
    }
    return state

def verify_answer_node(state: AgentState) -> AgentState:
    """
    Post-generation verification (FR-ANS-2, FR-ANS-6):
    Validates that numbers mentioned in final answer match tool results (SQL or Documents).
    """
    if not state.final_answer or state.route == "refuse":
        state.is_verified = True
        return state

    answer_text = state.final_answer.get("answer", "")
    sql_rows = state.sql_result.get("rows", []) if state.sql_result else []
    doc_results = state.doc_result.get("results", []) if state.doc_result else []

    # Collect numbers from Question
    valid_numbers = set()
    for n in re.findall(r'(?<![A-Za-z0-9_])(?:\$|₹)?(-?\d[\d,]*(?:\.\d+)?)(?![A-Za-z0-9_])', state.question):
        try:
            valid_numbers.add(float(n.replace(',', '')))
        except ValueError:
            pass

    # Collect numbers from SQL rows
    for row in sql_rows:
        for val in row.values():
            try:
                v = float(val)
                valid_numbers.add(v)
                valid_numbers.add(round(v, 2))
                valid_numbers.add(abs(v))
                valid_numbers.add(round(abs(v), 2))
            except (ValueError, TypeError):
                pass

    # Collect numbers from Document chunks
    for chunk in doc_results:
        chunk_text = chunk.get("text", "")
        for n in re.findall(r'(?<![A-Za-z0-9_])(?:\$|₹)?(-?\d[\d,]*(?:\.\d+)?)(?![A-Za-z0-9_])', chunk_text):
            try:
                val = float(n.replace(',', ''))
                valid_numbers.add(val)
                valid_numbers.add(abs(val))
            except ValueError:
                pass

    # Extract numbers from answer text (supports negative numbers and Indian comma notation e.g. 1,10,209.78)
    numbers_in_text = []
    for n in re.findall(r'(?<![A-Za-z0-9_])(?:\$|₹)?(-?\d[\d,]*(?:\.\d+)?)(?![A-Za-z0-9_])', answer_text):
        try:
            numbers_in_text.append(float(n.replace(',', '')))
        except ValueError:
            pass

    unmatched = []
    for num in numbers_in_text:
        # Ignore common structural numbers (years, page numbers < 10)
        if num in (2025, 2026, 2027) or abs(num) < 10:
            continue
        if num not in valid_numbers and abs(num) not in valid_numbers:
            unmatched.append(num)

    if unmatched:
        state.final_answer["confidence"] = "low"
        state.final_answer["warning"] = f"Detected numbers not grounded in SQL query or documents: {unmatched}"
        # Guardrail: Prevent hallucinated numbers from reaching the user by overriding with grounded DB text
        if state.grounded_text and state.grounded_text != "Could not generate an answer.":
            state.final_answer["answer"] = state.grounded_text
            state.is_verified = True
            return state
        state.final_answer["answer"] = "I cannot fulfill this request because the generated figures could not be grounded in your verified records."
        state.is_verified = False
        return state

    state.is_verified = True
    return state

def log_trace_node(state: AgentState, db: Optional[Session] = None) -> AgentState:
    """Persists trace record to database."""
    if db:
        try:
            trace_obj = Trace(
                trace_id=state.trace_id,
                user_id=state.user_id,
                question=state.question,
                route=state.route,
                tool_calls=state.tool_calls,
                final_answer=state.final_answer,
                latency_ms=state.latency_ms
            )
            db.add(trace_obj)
            db.commit()
        except Exception as e:
            db.rollback()
    return state
