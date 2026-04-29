"""
config.py
---------
Central configuration management using Pydantic BaseSettings.
All environment variables are loaded from a .env file.

Interview talking point:
    "I used Pydantic BaseSettings to provide type-safe, validated config
     loading — the same pattern used in production FastAPI applications."
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment / .env file."""

    # ── API Keys ─────────────────────────────────────────────────────────────
    google_api_key: str = Field(
        ...,               # Required — will raise error if missing
        description="Google AI Studio API key for Gemini LLM + Embeddings"
    )
    tavily_api_key: str = Field(
        default="",
        description="Tavily search API key (optional, falls back to DuckDuckGo)"
    )

    # ── LLM Configuration ────────────────────────────────────────────────────
    # Planner + Reviewer use the Pro model (better reasoning)
    # Executor uses Flash (faster code generation, cheaper)
    llm_model_pro: str = "gemini-1.5-pro"
    llm_model_fast: str = "gemini-1.5-flash"
    embedding_model: str = "models/text-embedding-004"

    llm_temperature: float = 0.1       # Low temperature = more deterministic output

    # ── RAG Configuration ────────────────────────────────────────────────────
    chunk_size: int = 1000             # Tokens per chunk
    chunk_overlap: int = 150           # Overlap prevents context loss at boundaries
    retrieval_k: int = 6               # Number of chunks to retrieve per query

    # ── Paths ─────────────────────────────────────────────────────────────────
    chroma_persist_dir: str = "./chroma_db"
    managed_projects_dir: str = "./managed_projects"
    active_project_state_file: str = "./managed_projects/active_project.json"
    run_history_dir: str = "./managed_projects/run_history"

    # ── Agent Loop Config ─────────────────────────────────────────────────────
    max_review_iterations: int = 3     # Max retry loops before escalating

    # ── Dev Settings ─────────────────────────────────────────────────────────
    debug: bool = True

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("debug", mode="before")
    @classmethod
    def normalize_debug_flag(cls, value: object) -> bool | object:
        """
        Accept common deployment-style debug values.

        Some environments use strings like 'release' or 'debug' instead of
        strict booleans. Normalize those here so startup remains predictable.
        """
        if isinstance(value, str):
            normalized = value.strip().lower()
            truthy = {"1", "true", "yes", "on", "debug", "dev", "development"}
            falsy = {"0", "false", "no", "off", "release", "prod", "production"}

            if normalized in truthy:
                return True
            if normalized in falsy:
                return False

        return value


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return a cached Settings singleton.
    lru_cache ensures we only read the .env file once per application start.
    """
    return Settings()


# Convenience export for direct imports: `from backend.config import settings`
settings = get_settings()
