"""Minimalist Agentic Harness — CIV Pattern Implementation."""

__version__ = "0.2.0"

from .client import InferenceClient
from .config import HarnessConfig, load_config
from .context import ContextManager
from .executor import ToolExecutor
from .orchestrator import Orchestrator, OrchestratorResult, TaskResult
from .schemas import (
    AgentAction,
    Task,
    TaskPlan,
    TaskStatus,
    ToolCall,
    VerificationResult,
)

__all__ = [
    "AgentAction",
    "ContextManager",
    "HarnessConfig",
    "InferenceClient",
    "Orchestrator",
    "OrchestratorResult",
    "Task",
    "TaskPlan",
    "TaskResult",
    "TaskStatus",
    "ToolCall",
    "ToolExecutor",
    "VerificationResult",
    "load_config",
]
