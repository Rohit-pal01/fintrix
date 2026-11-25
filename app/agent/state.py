"""Agent State Definition for LangGraph Finance Copilot."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import uuid

class ToolCallRecord(BaseModel):
    tool: str
    input: Dict[str, Any]
    output: Any
    status: str = "success"

class AgentState(BaseModel):
    trace_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    question: str
    user_id: int = 1
    route: Optional[str] = None  # sql | documents | both | clarify | refuse
    plan: List[str] = Field(default_factory=list)
    step_count: int = 0
    max_steps: int = 6
    tool_calls: List[Dict[str, Any]] = Field(default_factory=list)
    sql_result: Optional[Dict[str, Any]] = None
    doc_result: Optional[Dict[str, Any]] = None
    grounded_text: Optional[str] = None
    final_answer: Optional[Dict[str, Any]] = None
    is_verified: bool = False
    error: Optional[str] = None
    latency_ms: int = 0
