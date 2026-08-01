"""Prompts subpackage: agent instruction strings kept separate from agent code."""

from .coding import CODING_AGENT_INSTRUCTIONS
from .documentation import DOCUMENTATION_AGENT_INSTRUCTIONS
from .planning import PLANNING_AGENT_INSTRUCTIONS
from .requirements import REQUIREMENTS_AGENT_INSTRUCTIONS
from .review import REVIEW_AGENT_INSTRUCTIONS

__all__ = [
    "CODING_AGENT_INSTRUCTIONS",
    "DOCUMENTATION_AGENT_INSTRUCTIONS",
    "PLANNING_AGENT_INSTRUCTIONS",
    "REQUIREMENTS_AGENT_INSTRUCTIONS",
    "REVIEW_AGENT_INSTRUCTIONS",
]
