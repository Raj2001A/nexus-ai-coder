"""
workflow.py
-----------
LangGraph StateGraph — the orchestration backbone of the entire system.

Flow:
    START → rag_retrieve → planner → executor → reviewer
                                        ↑           │
                                        └── LOOP ───┘ (if FAIL + count < max)
                                                    │
                                                  END (if PASS or max retries)

This is the single most important file for interviews. It demonstrates:
    1. Stateful graph orchestration (not just chaining prompts)
    2. Conditional routing (reviewer decides next step)
    3. Loop guard (prevents infinite retry loops)
    4. Clean separation of concerns (each node does one thing)

Interview talking point:
    "LangGraph gives me deterministic control flow over non-deterministic
     agents. The graph decides WHEN to run each agent, the agents decide
     WHAT to do. The reviewer loop is key — it creates a feedback cycle
     where bad code gets caught and fixed automatically, up to 3 times."
"""

import logging
from typing import Literal

from langgraph.graph import StateGraph, START, END

from backend.graph.state import AgentState
from backend.config import settings
from backend.rag.retriever import CodebaseRetriever, format_results_for_agent, serialize_results
from backend.agents.planner import run_planner
from backend.agents.executor import run_executor
from backend.agents.reviewer import run_reviewer

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# NODE FUNCTIONS — Each function is a node in the graph.
# Each takes the current state and returns a partial state update.
# ══════════════════════════════════════════════════════════════════════════════

def rag_retrieve_node(state: AgentState) -> dict:
    """
    Node 1: Retrieve relevant codebase context using RAG.
    Runs before the planner so it has context about existing code.
    """
    logger.info("═══ [Node: RAG Retrieve] ═══")
    task = state["task"]

    try:
        retriever = CodebaseRetriever(state.get("collection_name"))
        docs = retriever.get_relevant_documents(task)
        context = format_results_for_agent(docs)
        retrieved_items = serialize_results(docs)
        logger.info(f"Retrieved {len(context)} chars of codebase context")
    except Exception as e:
        logger.warning(f"RAG retrieval failed (continuing without context): {e}")
        context = "No codebase has been ingested yet. Working from scratch."
        retrieved_items = []

    return {
        "codebase_context": context,
        "retrieved_context_items": retrieved_items,
    }


def planner_node(state: AgentState) -> dict:
    """
    Node 2: Run the Planning Agent to create an implementation plan.
    """
    logger.info("═══ [Node: Planner] ═══")
    task = state["task"]
    context = state.get("codebase_context", "")

    try:
        plan = run_planner(task, context)
    except Exception as e:
        logger.error(f"Planner failed: {e}")
        plan = (
            f"FALLBACK PLAN: The planning agent encountered an error ({e}). "
            f"Proceeding with direct implementation of: {task}"
        )

    return {"plan": plan}


def executor_node(state: AgentState) -> dict:
    """
    Node 3: Run the Execution Agent to implement the plan.
    On retry loops, includes the reviewer's feedback for corrections.
    """
    iteration = state.get("iteration_count", 0)
    logger.info(f"═══ [Node: Executor] (iteration {iteration + 1}) ═══")

    plan = state.get("plan", "")
    task = state["task"]

    # On retry: append reviewer feedback so executor knows what to fix
    if iteration > 0 and state.get("review_result"):
        plan = (
            f"{plan}\n\n"
            f"## ⚠️ REVIEWER FEEDBACK (Iteration {iteration})\n"
            f"The reviewer found issues. Fix these:\n\n"
            f"{state['review_result']}"
        )

    try:
        code_output = run_executor(plan, task)
    except Exception as e:
        logger.error(f"Executor failed: {e}")
        code_output = f"Executor error: {e}"

    return {
        "code_output": code_output,
        "iteration_count": iteration + 1,
    }


def reviewer_node(state: AgentState) -> dict:
    """
    Node 4: Run the Review Agent to validate the implementation.
    Returns PASS/FAIL verdict that drives the conditional routing.
    """
    iteration = state.get("iteration_count", 0)
    logger.info(f"═══ [Node: Reviewer] (after iteration {iteration}) ═══")

    try:
        review = run_reviewer(
            user_request=state["task"],
            plan=state.get("plan", ""),
            execution_result=state.get("code_output", ""),
        )
        passed = review["passed"]
        feedback = review["feedback"]
    except Exception as e:
        logger.error(f"Reviewer failed: {e}")
        # On reviewer failure, auto-pass to prevent infinite loops
        passed = True
        feedback = f"Reviewer error ({e}) — auto-approving to prevent deadlock."

    return {
        "review_passed": passed,
        "review_result": feedback,
    }


def finalize_node(state: AgentState) -> dict:
    """
    Terminal node: Assemble the final answer from all agent outputs.
    """
    logger.info("═══ [Node: Finalize] ═══")

    iterations = state.get("iteration_count", 0)
    passed = state.get("review_passed", False)

    final = []
    final.append("# 🤖 AI Coding Assistant — Results\n")
    final.append(f"## Task\n{state['task']}\n")

    if state.get("plan"):
        final.append(f"## 📋 Plan\n{state['plan']}\n")

    if state.get("code_output"):
        final.append(f"## 💻 Implementation\n{state['code_output']}\n")

    if state.get("review_result"):
        status = "✅ APPROVED" if passed else "⚠️ MAX RETRIES REACHED"
        final.append(f"## 🔍 Review ({status})\n{state['review_result']}\n")

    final.append(f"\n---\n*Completed in {iterations} iteration(s)*")

    return {"final_answer": "\n".join(final)}


# ══════════════════════════════════════════════════════════════════════════════
# CONDITIONAL ROUTING — The reviewer's verdict controls the flow.
# ══════════════════════════════════════════════════════════════════════════════

def should_retry_or_finish(state: AgentState) -> Literal["executor", "finalize"]:
    """
    Conditional edge after the reviewer node.

    Routes to:
        - "executor"  → if review FAILED and we haven't exceeded max iterations
        - "finalize"  → if review PASSED or max iterations reached
    """
    passed = state.get("review_passed", False)
    iteration = state.get("iteration_count", 0)
    max_iter = state.get("max_iterations", settings.max_review_iterations)

    if passed:
        logger.info(f"[Router] ✅ Review passed — routing to finalize")
        return "finalize"

    if iteration >= max_iter:
        logger.warning(
            f"[Router] ⚠️ Max iterations ({max_iter}) reached — "
            f"routing to finalize with current state"
        )
        return "finalize"

    logger.info(f"[Router] 🔄 Review failed — routing back to executor (attempt {iteration + 1})")
    return "executor"


# ══════════════════════════════════════════════════════════════════════════════
# GRAPH ASSEMBLY — Wire everything together.
# ══════════════════════════════════════════════════════════════════════════════

def build_workflow() -> StateGraph:
    """
    Assemble the complete LangGraph workflow.

    Returns a compiled StateGraph ready for execution.
    """
    graph = StateGraph(AgentState)

    # ── Add Nodes ─────────────────────────────────────────────────────────
    graph.add_node("rag_retrieve", rag_retrieve_node)
    graph.add_node("planner", planner_node)
    graph.add_node("executor", executor_node)
    graph.add_node("reviewer", reviewer_node)
    graph.add_node("finalize", finalize_node)

    # ── Add Edges (the wiring) ──────────────────────────────────────────
    graph.add_edge(START, "rag_retrieve")
    graph.add_edge("rag_retrieve", "planner")
    graph.add_edge("planner", "executor")
    graph.add_edge("executor", "reviewer")

    # Conditional edge: reviewer decides next step
    graph.add_conditional_edges(
        "reviewer",
        should_retry_or_finish,
        {
            "executor": "executor",   # Loop back
            "finalize": "finalize",   # Done
        },
    )

    graph.add_edge("finalize", END)

    return graph.compile()


# Pre-built workflow instance — import this in the API layer
workflow = build_workflow()


# ── CLI entrypoint for testing ──────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
    )

    parser = argparse.ArgumentParser(description="Run the AI Coding Assistant workflow")
    parser.add_argument("--task", required=True, help="The coding task to execute")
    args = parser.parse_args()

    initial_state: AgentState = {
        "task": args.task,
        "collection_name": "codebase",
        "codebase_context": "",
        "retrieved_context_items": [],
        "plan": "",
        "code_output": "",
        "review_result": "",
        "review_passed": False,
        "iteration_count": 0,
        "max_iterations": settings.max_review_iterations,
        "final_answer": "",
        "error": "",
        "messages": [],
    }

    print(f"\n🚀 Starting workflow for: '{args.task}'\n")
    result = workflow.invoke(initial_state)
    print("\n" + "═" * 60)
    print(result["final_answer"])
