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

        if state.route in ("documents", "both") and self.retriever is not None:
            state = retrieve_docs_node(state, self.retriever)

        # Step 3: Compose Answer
        state = compose_answer_node(state)

        # Step 4: Verify Grounding
        state = verify_answer_node(state)

        # Step 5: Log Observability Trace
        state.latency_ms = int((time.time() - start_time) * 1000)
        return log_trace_node(state, db)
