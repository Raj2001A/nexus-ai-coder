"""
state.py
--------
Defines the shared state schema for the LangGraph workflow.

Every node in the graph reads from and writes to this state object.
LangGraph manages checkpointing and persistence automatically.

Interview talking point:
    "I used a TypedDict state schema so every node has a clear contract —
     the planner writes the 'plan' field, the executor writes 'code_output',
     and the reviewer writes 'review_result'. This makes the system debuggable
     and testable at every stage."
"""

from typing import TypedDict, List, Optional, Annotated
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
    Shared state passed between all nodes in the LangGraph workflow.

    Fields:
        task:              The original user request.
        collection_name:   Active Chroma collection used for retrieval.
        codebase_context:  RAG-retrieved code chunks (set by rag_retrieve node).
        retrieved_context_items: Structured retrieval items for UI/reporting.
        plan:              Structured implementation plan (set by planner node).
        code_output:       Executor's implementation report (set by executor node).
        review_result:     Reviewer's feedback text (set by reviewer node).
        review_passed:     Whether the reviewer approved (set by reviewer node).
        iteration_count:   Current review loop iteration (for loop guard).
        max_iterations:    Maximum review loops before forcing completion.
        final_answer:      The consolidated answer returned to the user.
        error:             Error message if something went wrong.
        messages:          Chat history (LangGraph convention).
    """
    task: str
    collection_name: str
    codebase_context: str
    retrieved_context_items: list[dict]
    plan: str
    code_output: str
    review_result: str
    review_passed: bool
    iteration_count: int
    max_iterations: int
    final_answer: str
    error: str
    messages: Annotated[List[BaseMessage], add_messages]
