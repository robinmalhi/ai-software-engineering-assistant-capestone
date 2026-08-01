from agents import Agent

from ai_assistant.prompts import REQUIREMENTS_AGENT_INSTRUCTIONS

requirements_agent = Agent(
    name="Requirements Analysis Agent",
    instructions=REQUIREMENTS_AGENT_INSTRUCTIONS,
)
