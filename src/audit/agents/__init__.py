"""Audit Agents Package."""

from .base import BaseAgent, AgentResult
from .content import ContentAgent
from .business import BusinessAgent
from .technical import TechnicalAgent
from .performance import PerformanceAgent

AGENT_REGISTRY: dict[str, type[BaseAgent]] = {
    "content": ContentAgent,
    "business": BusinessAgent,
    "technical": TechnicalAgent,
    "performance": PerformanceAgent,
}


def get_agent(agent_name: str, config: dict) -> BaseAgent:
    """Factory function to create agent instances."""
    agent_class = AGENT_REGISTRY.get(agent_name)
    if not agent_class:
        raise ValueError(
            f"Unknown agent: {agent_name}. Available: {list(AGENT_REGISTRY.keys())}"
        )
    return agent_class(config)


__all__ = [
    "BaseAgent",
    "AgentResult",
    "ContentAgent",
    "BusinessAgent",
    "TechnicalAgent",
    "PerformanceAgent",
    "get_agent",
    "AGENT_REGISTRY",
]
