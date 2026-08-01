from agents import Agent

from ai_assistant.prompts import DOCUMENTATION_AGENT_INSTRUCTIONS

documentation_agent = Agent(
    name="Documentation Agent",
    instructions=DOCUMENTATION_AGENT_INSTRUCTIONS,
)
