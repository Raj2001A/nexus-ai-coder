"""
Execution agent definition.

Phase 2 intent:
the executor now operates against the active project rather than an isolated workspace.
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
from backend.tools.doc_search import search_docs
from backend.tools.file_ops import (
    list_files,
    read_code,
    replace_code_block,
    replace_code_lines,
    save_code,
    search_workspace,
)

logger = logging.getLogger(__name__)


def _get_executor_llm() -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=settings.llm_model_fast,
        google_api_key=settings.google_api_key,
        temperature=settings.llm_temperature,
        convert_system_message_to_human=True,
    )


def create_executor_agent() -> Agent:
    return Agent(
        role="Senior Software Engineer",
        goal=(
            "Implement coding tasks by writing clean, well-documented code in the active project. "
            "Follow the plan exactly. Write code to files, run it to verify it works, "
            "and fix any errors you encounter."
        ),
        backstory=(
            "You are a senior software engineer who writes production-quality code. "
            "You read the existing repository before making changes, preserve project conventions, "
            "and verify behavior after editing."
        ),
        tools=[
            search_codebase,
            read_code,
            replace_code_block,
            replace_code_lines,
            save_code,
            list_files,
            search_workspace,
            run_python_code,
            run_javascript_code,
            run_typescript_code,
            run_existing_file,
            run_project_command,
            search_docs,
        ],
        llm=_get_executor_llm(),
        verbose=settings.debug,
        allow_delegation=False,
        max_iter=15,
    )


def create_execution_task(agent: Agent, plan: str, user_request: str) -> Task:
    return Task(
        description=(
            f"## Original User Request\n{user_request}\n\n"
            f"## Implementation Plan to Follow\n{plan}\n\n"
            "## Your Task\n"
            "Follow the implementation plan step by step:\n\n"
            "1. For each step in the plan:\n"
            "   a. Use `search_codebase` if you need to understand existing code\n"
            "   b. Use `read_code` before editing files that already exist\n"
            "   c. Prefer targeted edits for existing files:\n"
            "      - `replace_code_block` when you know the exact snippet to change\n"
            "      - `replace_code_lines` when you know the line range to update\n"
            "      - use `save_code` for new files or deliberate full-file rewrites only\n"
            "   d. Choose the right verification path for the stack:\n"
            "      - `run_python_code` for Python snippets\n"
            "      - `run_javascript_code` for JavaScript snippets\n"
            "      - `run_typescript_code` for TypeScript snippets\n"
            "      - `run_existing_file` for existing project files\n"
            "      - `run_project_command` for repo-local test/build commands\n"
            "   e. If tests fail, read the error and fix the code\n\n"
            "2. After all steps are complete:\n"
            "   a. Use `list_files` to show the final project structure\n"
            "   b. Provide a summary of what you changed and how you verified it\n\n"
            "## Code Quality Requirements\n"
            "- Include type hints on function signatures where appropriate\n"
            "- Add docstrings to functions and classes where appropriate\n"
            "- Handle errors gracefully with meaningful messages\n"
            "- Use meaningful variable and function names\n"
            "- Avoid whole-file rewrites when a targeted patch is sufficient\n"
        ),
        expected_output=(
            "A summary of files created or modified, with confirmation "
            "that the implementation was tested and what the outcome was."
        ),
        agent=agent,
    )


def run_executor(plan: str, user_request: str) -> str:
    logger.info("[Executor] Starting execution phase.")

    agent = create_executor_agent()
    task = create_execution_task(agent, plan, user_request)

    crew = Crew(
        agents=[agent],
        tasks=[task],
        process=Process.sequential,
        verbose=settings.debug,
    )

    output = retry_crew_execution(crew, max_attempts=5)

    logger.info(f"[Executor] Execution complete ({len(output)} chars)")
    return output
