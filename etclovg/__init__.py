"""
ETCLOVG Harness — A Production-Grade Agent Harness Framework

Implements the complete seven-layer ETCLOVG architecture derived from
analysis of 170+ open-source agent frameworks, Anthropic Managed Agents,
GenericAgent, OpenClaw, Hermes Agent, and benchmark-evaluated systems.

Seven Layers:
  E — Execution Environment & Sandbox (7 sandbox types)
  T — Tool Interface & Protocol (MCP/A2A/Function Calling/OpenAPI)
  C — Context Management (short/mid/long-term memory)
  L — Lifecycle & Orchestration (plan/execute/reflect loops)
  O — Observability (tracing/cost/reliability)
  V — Verification & Evaluation (task→feedback lifecycle)
  G — Governance & Security (permissions/hooks/constitutional AI)
"""

__version__ = "1.0.0"
__author__ = "ETCLOVG Harness Contributors"
__license__ = "Apache-2.0"

from etclovg.harness import ETCLOVGHarness
from etclovg.e_layer.sandbox import SandboxRegistry
from etclovg.t_layer.registry import ToolRegistry
from etclovg.c_layer.memory import ContextManager
from etclovg.l_layer.orchestrator import Orchestrator
from etclovg.o_layer.telemetry import Telemetry
from etclovg.v_layer.evaluator import Evaluator
from etclovg.g_layer.governor import Governor

__all__ = [
    "ETCLOVGHarness",
    "SandboxRegistry",
    "ToolRegistry",
    "ContextManager",
    "Orchestrator",
    "Telemetry",
    "Evaluator",
    "Governor",
]
