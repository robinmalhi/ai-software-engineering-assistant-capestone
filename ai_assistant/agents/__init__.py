"""Agents subpackage: OpenAI Agents SDK agent definitions.

Each agent module imports its instruction strings from :mod:`ai_assistant.prompts`
so prompt engineering concerns stay separated from agent construction.
"""

from .coding_agent import coding_agent
from .documentation_agent import documentation_agent
from .planning_agent import planning_agent
from .requirements_agent import requirements_agent
from .review_agent import review_agent

__all__ = [
    "coding_agent",
    "documentation_agent",
    "planning_agent",
    "requirements_agent",
    "review_agent",
]
