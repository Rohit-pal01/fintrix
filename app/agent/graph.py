"""LangGraph Agent Orchestrator & State Flow."""
import time
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from app.agent.state import AgentState
from app.agent.nodes import (
    classify_and_plan_node, execute_sql_node, retrieve_docs_node,
    compose_answer_node, verify_answer_node, log_trace_node
)
from app.tools.doc_tool import DocumentRetriever

class FinanceCopilotAgent:
    """Orchestrates LangGraph execution loop for verifiable answers."""
    def __init__(self, retriever: Optional[DocumentRetriever] = None):
        self.retriever = retriever

    def run(self, question: str, user_id: int = 1, db: Optional[Session] = None) -> AgentState:
        start_time = time.time()
        state = AgentState(question=question, user_id=user_id)

        # Step 1: Classify and Plan
        state = classify_and_plan_node(state)
        if state.route == "refuse":
            state.latency_ms = int((time.time() - start_time) * 1000)
            return log_trace_node(state, db)

        # Step 2: Tool Execution
        if state.route in ("sql", "both") and db is not None:
            state = execute_sql_node(state, db)

        # Smart Bidirectional Fallback Loop:
        # If SQL was executed but yielded 0 rows, or if SQL returned internal database row IDs
        # when the user was asking for statement metadata, automatically fallback to search documents.
        sql_empty = False
        if state.route == "sql" and state.sql_result:
            if state.sql_result.get("row_count", 0) == 0:
                sql_empty = True
            rows = state.sql_result.get("rows", [])
            if rows and len(rows) == 1:
                first_row_keys = list(rows[0].keys())
                if first_row_keys in (["account_id"], ["name"]):
                    q_lower = state.question.lower()
                    if any(k in q_lower for k in ["account no", "account number", "acc no", "a/c", "holder name", "customer name"]):
                        sql_empty = True

        if (state.route in ("documents", "both") or sql_empty) and self.retriever is not None:
            state = retrieve_docs_node(state, self.retriever)

        # Reverse Fallback: If document search found 0 results, check SQL as backup
        doc_empty = False
        if state.route == "documents" and state.doc_result:
            if not state.doc_result.get("results"):
                doc_empty = True

        if doc_empty and db is not None and not state.sql_result:
            state = execute_sql_node(state, db)

        # Step 3: Compose Answer
        state = compose_answer_node(state)

        # Step 4: Verify Grounding
        state = verify_answer_node(state)

        # Step 5: Log Observability Trace
        state.latency_ms = int((time.time() - start_time) * 1000)
        return log_trace_node(state, db)
