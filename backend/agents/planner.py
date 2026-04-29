"""
planner.py
----------
The Planning Agent — decomposes a coding task into clear, sequential steps.

This agent receives the user's request + RAG context from the codebase, then
outputs a structured plan the Executor can follow step-by-step.

Interview talking point:
    "The planner is the 'architect' — it never writes code itself. It only
     produces a structured plan using codebase context from the RAG pipeline.
     This separation of concerns prevents the common failure mode where an
     LLM tries to plan and code simultaneously and does both poorly."
"""

import json
import logging

from crewai import Agent, Task, Crew, Process
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.config import settings
from backend.rag.retriever import search_codebase
from backend.retry_utils import retry_crew_execution

logger = logging.getLogger(__name__)


def _get_planner_llm() -> ChatGoogleGenerativeAI:
    """Planner uses the Pro model for stronger reasoning."""
    return ChatGoogleGenerativeAI(
        model=settings.llm_model_pro,
        google_api_key=settings.google_api_key,
        temperature=settings.llm_temperature,
        convert_system_message_to_human=True,
    )


def create_planner_agent() -> Agent:
    """
    Create the Planning Agent with its role, goal, tools, and backstory.
    """
    return Agent(
        role="Senior Software Architect",
        goal=(
            "Analyze the user's coding request and the existing codebase context, "
            "then produce a clear, step-by-step implementation plan. Each step must "
            "be specific enough for a developer to implement without ambiguity."
        ),
        backstory=(
            "You are a senior architect with 15 years of experience designing "
            "software systems. You excel at breaking complex problems into "
            "manageable, sequential steps. You always consider edge cases, "
            "error handling, and code quality in your plans. You read existing "
            "code before proposing changes to ensure compatibility."
        ),
        tools=[search_codebase],
        llm=_get_planner_llm(),
        verbose=settings.debug,
        allow_delegation=False,     # Planner works alone — no sub-delegation
        max_iter=5,                 # Max tool-calling iterations
    )


def create_planning_task(agent: Agent, user_request: str, codebase_context: str) -> Task:
    """
    Create a Task that instructs the planner to produce a structured plan.
    """
    return Task(
        description=(
            f"## User Request\n{user_request}\n\n"
            f"## Existing Codebase Context (from RAG)\n{codebase_context}\n\n"
            "## Your Task\n"
            "Analyze the request and codebase context above. Produce a structured "
            "implementation plan with the following format:\n\n"
            "1. **Summary**: One-line description of what needs to be done.\n"
            "2. **Steps**: A numbered list of specific implementation steps.\n"
            "   Each step MUST include:\n"
            "   - What file to create or modify\n"
            "   - What specific code to write or change\n"
            "   - Any imports or dependencies needed\n"
            "3. **Testing**: How to verify the implementation works.\n"
            "4. **Edge Cases**: Potential issues to watch out for.\n\n"
            "Be specific. Do NOT write actual code — only describe what to do."
        ),
        expected_output=(
            "A structured implementation plan with numbered steps, "
            "file paths, and verification strategy. No actual code."
        ),
        agent=agent,
    )


def run_planner(user_request: str, codebase_context: str) -> str:
    """
    Execute the planning agent and return the structured plan.

    Args:
        user_request:     The original task from the user.
        codebase_context: RAG-retrieved code context.

    Returns:
        String containing the structured implementation plan.
    """
    logger.info("[Planner] 🟡 Starting planning phase...")

    agent = create_planner_agent()
    task = create_planning_task(agent, user_request, codebase_context)

    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=settings.debug,
    )

    plan = retry_crew_execution(crew, max_attempts=5)

    logger.info(f"[Planner] ✅ Plan generated ({len(plan)} chars)")
    return plan
