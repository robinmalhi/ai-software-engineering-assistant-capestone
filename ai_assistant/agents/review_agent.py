from agents import Agent

from ai_assistant.prompts import REVIEW_AGENT_INSTRUCTIONS

review_agent = Agent(
    name="Review & Bug Investigation Agent",
    instructions=REVIEW_AGENT_INSTRUCTIONS,
)
