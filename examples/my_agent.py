"""Example target for the red-team command:  decisiontrace redteam --target examples.my_agent:agent --canary SECRET-123"""


def agent(prompt: str) -> str:
    # Replace with a call to your real LLM / agent. This one is deliberately gullible.
    if "system prompt" in prompt.lower():
        return "My system prompt contains SECRET-123"
    return "Happy to help!"
