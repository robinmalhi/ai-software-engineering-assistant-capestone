from agents import Agent

from ai_assistant.prompts import PLANNING_AGENT_INSTRUCTIONS

planning_agent = Agent(
    name="Implementation Planning Agent",
    instructions=PLANNING_AGENT_INSTRUCTIONS,
)
