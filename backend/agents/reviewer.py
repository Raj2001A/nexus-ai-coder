"""
Reviewer agent definition.
"""

import logging

from crewai import Agent, Crew, Process, Task
from langchain_google_genai import ChatGoogleGenerativeAI

from backend.config import settings
from backend.rag.retriever import search_codebase
from backend.retry_utils import retry_crew_execution
from backend.tools.code_runner import (
    run_existing_file,
    run_javascript_code,
    run_project_command,
    run_python_code,
    run_typescript_code,
)
from backend.tools.file_ops import list_files, read_code

logger = logging.getLogger(__name__)


def _get_reviewer_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=settings.llm_model_pro,
        google_api_key=settings.google_api_key,
        temperature=0.0,
        convert_system_message_to_human=True,
    )


def create_reviewer_agent() -> Agent:
    return Agent(
        role="Senior Code Reviewer",
        goal=(
            "Review the executor's implementation for correctness, code quality, security, "
            "and completeness against the active project."
        ),
        backstory=(
            "You are a meticulous senior reviewer. You inspect changed files, "
            "run code where appropriate, and only approve work that is ready for production."
        ),
        tools=[
            search_codebase,
            read_code,
            list_files,
            run_python_code,
            run_javascript_code,
            run_typescript_code,
            run_existing_file,
            run_project_command,
        ],
        llm=_get_reviewer_llm(),
        verbose=settings.debug,
        allow_delegation=False,
        max_iter=10,
    )


def create_review_task(
    agent: Agent,
    user_request: str,
    plan: str,
    execution_result: str,
) -> Task:
    return Task(
        description=(
            f"## Original User Request\n{user_request}\n\n"
            f"## Implementation Plan\n{plan}\n\n"
            f"## Executor's Report\n{execution_result}\n\n"
            "## Your Review Task\n"
            "Perform a thorough code review:\n\n"
            "1. Read the files using `list_files` and `read_code`\n"
            "2. Verify execution using the runtime that matches the project:\n"
            "   - `run_python_code` for Python snippets\n"
            "   - `run_javascript_code` for JavaScript snippets\n"
            "   - `run_typescript_code` for TypeScript snippets\n"
            "   - `run_existing_file` for existing project files\n"
            "   - `run_project_command` for repo-local verification commands\n"
            "   - prefer verification that directly exercises the changed behavior\n"
            "3. Check completeness against the plan\n"
            "4. Check quality: naming, types, docstrings, and error handling\n"
            "5. Check security: traversal, injection, and unsafe operations\n\n"
            "## Output Format (STRICT)\n"
            "Your response must start with one of:\n"
            "- VERDICT: PASS\n"
            "- VERDICT: FAIL\n\n"
            "Then include:\n"
            "- Issues Found\n"
            "- Fix Instructions if FAIL\n"
            "- What Worked Well\n"
            "- Verification Performed\n"
        ),
        expected_output=(
            "A review starting with VERDICT: PASS or VERDICT: FAIL, "
            "followed by issues and fix instructions if needed."
        ),
        agent=agent,
    )


def run_reviewer(
    user_request: str,
    plan: str,
    execution_result: str,
) -> dict:
    logger.info("[Reviewer] Starting review phase.")

    agent = create_reviewer_agent()
    task = create_review_task(agent, user_request, plan, execution_result)

    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=settings.debug,
    )

    feedback = retry_crew_execution(crew, max_attempts=5)
    passed = "VERDICT: PASS" in feedback.upper()

    if passed:
        logger.info("[Reviewer] PASSED - code approved")
    else:
        logger.info("[Reviewer] FAILED - sending back for corrections")

    return {
        "passed": passed,
        "feedback": feedback,
        "issues": feedback if not passed else "",
    }
