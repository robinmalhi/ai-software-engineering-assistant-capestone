"""Settings, constants, and environment variable handling.

Keeps environment concerns out of the workflow and agent modules, and gives
us a single place to extend with model names, tracing flags, feature toggles,
or additional providers later.
"""

import os
from typing import Final

from dotenv import load_dotenv

# Default issue used by the CLI entrypoint if no input is provided.
DEFAULT_ISSUE: Final[str] = """
Add user authentication using JWT.
Users should be able to sign up, log in, and reset their passwords.
"""

# GitHub REST API entrypoint. Centralized so it can be swapped for GitHub
# Enterprise later by overriding GITHUB_API_BASE_URL.
GITHUB_API_BASE_URL: Final[str] = os.getenv(
    "GITHUB_API_BASE_URL", "https://api.github.com"
).rstrip("/")


def load_settings() -> None:
    """Load environment variables from .env into the process.

    Safe to call multiple times; dotenv handles re-entrancy and falls back
    gracefully when no .env file is present (host env vars still apply).
    """
    load_dotenv()


def get_openai_api_key() -> str:
    """Return the configured OpenAI API key, or raise if it is missing."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Configure it in a root .env file or "
            "export it as an environment variable."
        )
    return key


def get_github_token() -> str | None:
    """Return the optional GitHub token from the environment.

    A token is not required for public repos (anonymous rate limits apply),
    but is required for private repos and for higher rate limits.
    """
    return os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN") or None
