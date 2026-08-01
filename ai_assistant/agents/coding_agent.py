from agents import Agent

from ai_assistant.prompts import CODING_AGENT_INSTRUCTIONS

coding_agent = Agent(
    name="Coding Assistant Agent",
    instructions=CODING_AGENT_INSTRUCTIONS,
)
