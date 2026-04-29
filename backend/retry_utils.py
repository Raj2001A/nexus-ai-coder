"""
retry_utils.py
--------------
Utilities for handling API retries with exponential backoff.

This module provides decorators and wrappers for handling transient failures
from external APIs like Google Gemini, which may return "servers experiencing
high traffic" errors during peak load.
"""

import logging
import time
from functools import wraps
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)


class APITemporarilyUnavailable(Exception):
    """Raised when API returns a temporary error (e.g., high traffic)."""
    pass


def is_transient_error(exception: Exception) -> bool:
    """
    Determine if an exception represents a transient API error.
    
    Transient errors should be retried; permanent errors should fail immediately.
    """
    error_msg = str(exception).lower()
    
    transient_patterns = [
        "high traffic",
        "service unavailable",
        "temporarily unavailable",
        "internal server error",
        "too many requests",
        "rate limit",
        "timeout",
        "connection error",
        "temporarily overloaded",
    ]
    
    for pattern in transient_patterns:
        if pattern in error_msg:
            logger.warning(f"[Retry] Detected transient error: {error_msg[:100]}")
            return True
    
    return False


def with_exponential_backoff(max_attempts: int = 5, initial_wait: float = 1.0):
    """
    Decorator to add exponential backoff retry logic to a function.
    
    Args:
        max_attempts: Maximum number of retry attempts
        initial_wait: Initial wait time in seconds (will increase exponentially)
    
    Usage:
        @with_exponential_backoff(max_attempts=5)
        def my_api_call():
            ...
    """
    def decorator(func):
        @retry(
            stop=stop_after_attempt(max_attempts),
            wait=wait_exponential(multiplier=1, min=initial_wait, max=32),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator


def retry_crew_execution(crew, max_attempts: int = 5) -> str:
    """
    Execute a crew with exponential backoff retry logic.
    
    This wrapper handles transient API failures gracefully by retrying
    with exponential backoff when the API is temporarily overloaded.
    
    Args:
        crew: CrewAI Crew instance to execute
        max_attempts: Maximum number of retry attempts
    
    Returns:
        String result from crew execution
    
    Raises:
        Exception: If all retries fail
    """
    last_exception = None
    
    for attempt in range(1, max_attempts + 1):
        try:
            logger.info(f"[Crew] Execution attempt {attempt}/{max_attempts}")
            result = crew.kickoff()
            logger.info(f"[Crew] ✅ Execution succeeded on attempt {attempt}")
            return str(result)
        
        except Exception as e:
            last_exception = e
            
            if is_transient_error(e):
                if attempt < max_attempts:
                    wait_time = initial_wait_with_jitter(attempt)
                    logger.warning(
                        f"[Crew] Transient error on attempt {attempt}: {str(e)[:100]}. "
                        f"Retrying in {wait_time:.1f}s..."
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    logger.error(
                        f"[Crew] ❌ All {max_attempts} retry attempts exhausted. "
                        f"Last error: {str(e)[:100]}"
                    )
                    raise
            else:
                # Permanent error, fail immediately
                logger.error(f"[Crew] ❌ Permanent error (not retrying): {str(e)[:100]}")
                raise
    
    if last_exception:
        raise last_exception


def initial_wait_with_jitter(attempt: int, base_wait: float = 1.0, max_wait: float = 32.0) -> float:
    """
    Calculate exponential backoff with jitter to avoid thundering herd.
    
    Formula: min(max_wait, base_wait * 2^attempt) + random jitter (0-1s)
    """
    import random
    
    exponential_wait = min(max_wait, base_wait * (2 ** (attempt - 1)))
    jitter = random.uniform(0, 1.0)
    return exponential_wait + jitter
