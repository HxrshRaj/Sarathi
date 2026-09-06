from __future__ import annotations


class AgentError(Exception):
    """Raised by an agent when it cannot complete its step.

    `category` maps to agent_runs.error_category and the API error taxonomy:
    agent | tool | model | model_invalid_output | sandbox | limit_exceeded |
    cancelled | infra.
    """

    def __init__(self, message: str, *, category: str = "agent") -> None:
        super().__init__(message)
        self.category = category
