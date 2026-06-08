"""
ETCLOVG Harness — The Complete Seven-Layer Agent Orchestrator

This is the central integration point that wires together all seven
ETCLOVG layers into a production-ready agent execution environment.

  E — Subprocess sandbox with resource limits
  T — Multi-protocol tool registry (MCP / Function Calling / Local)
  C — Three-tier context manager with incremental compression
  L — Plan-Execute-Reflect orchestrator with budget enforcement
  O — Telemetry with tracing, cost tracking, and stall detection
  V — Preflight validation, posthoc verification, regression harness
  G — Four-layer defense-in-depth governance

Usage:
    from etclovg import ETCLOVGHarness

    harness = ETCLOVGHarness(api_key=os.environ["OPENAI_API_KEY"])
    harness.register_tool(my_function, name="search", description="Search the web")
    result = harness.run("What is the capital of France?")
    print(result["output"])
"""

from __future__ import annotations

import os
import json
import time
import logging
from typing import Any, Callable, Dict, List, Optional, Union

# OpenAI client (optional — only imported when needed)
try:
    from openai import OpenAI as OpenAIClient
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

from etclovg.e_layer.sandbox import (
    SandboxRegistry, SandboxBackend, ResourceLimits, SandboxCapability,
)
from etclovg.t_layer.registry import (
    ToolRegistry, ToolDefinition, ToolRisk, ToolProtocol, tool,
)
from etclovg.c_layer.memory import (
    ContextManager, Message, ShortTermMemory,
)
from etclovg.l_layer.orchestrator import (
    Orchestrator, IterationBudget, AgentState, AgentError,
)
from etclovg.o_layer.telemetry import Telemetry
from etclovg.v_layer.evaluator import Evaluator
from etclovg.g_layer.governor import (
    Governor, SecurityPolicy, ApprovalLevel, ToolRiskCategory,
)


# ======================================================================
# OpenAI LLM Client Adapter
# ======================================================================

class OpenAIAdapter:
    """
    Provider adapter: wraps openai.ChatCompletion into the Orchestrator's
    expected chat(messages, tools) → response interface.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        base_url: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ):
        if not OPENAI_AVAILABLE:
            raise ImportError(
                "openai package is required. Install with: pip install openai"
            )
        self.client = OpenAIClient(api_key=api_key, base_url=base_url)
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def chat(
        self,
        messages: List[dict],
        tools: Optional[List[dict]] = None,
        **kwargs: Any,
    ) -> dict:
        """Call OpenAI chat completion and return normalized response."""
        params = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            params["tools"] = tools
            params["tool_choice"] = "auto"

        params.update(kwargs)

        response = self.client.chat.completions.create(**params)
        choice = response.choices[0]
        message = choice.message

        result: dict = {
            "content": message.content or "",
            "role": "assistant",
            "model": response.model,
            "usage": {
                "input_tokens": response.usage.prompt_tokens if response.usage else 0,
                "output_tokens": response.usage.completion_tokens if response.usage else 0,
            },
        }

        # Normalize tool_calls format
        if message.tool_calls:
            result["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in message.tool_calls
            ]

        return result


# ======================================================================
# Default Tools
# ======================================================================

def _build_default_tools() -> List[Callable]:
    """Built-in tools every ETCLOVG agent should have."""
    tools = []

    def read_file(filepath: str) -> str:
        """Read the contents of a file from the local filesystem."""
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    def write_file(filepath: str, content: str) -> str:
        """Write content to a file on the local filesystem."""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"Successfully wrote {len(content)} characters to {filepath}"

    def list_directory(path: str = ".") -> str:
        """List files and directories at the given path."""
        import os
        items = os.listdir(path)
        return "\n".join(f"{'[DIR]' if os.path.isdir(os.path.join(path, i)) else '[FILE]'} {i}" for i in items)

    def search_memory(query: str) -> str:
        """Search the agent's long-term memory for relevant information. This function will be bound at harness init."""
        return f"[memory] Searching for: {query} (bound at runtime)"

    def get_time() -> str:
        """Get the current date and time."""
        from datetime import datetime
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z")

    def calculate(expression: str) -> str:
        """Evaluate a mathematical expression (supports +, -, *, /, **, %, parentheses)."""
        import ast
        import operator
        allowed = {
            ast.Add: operator.add, ast.Sub: operator.sub,
            ast.Mult: operator.mul, ast.Div: operator.truediv,
            ast.Pow: operator.pow, ast.Mod: operator.mod,
            ast.USub: operator.neg,
        }
        def _eval(node):
            if isinstance(node, ast.Expression):
                return _eval(node.body)
            if isinstance(node, ast.BinOp):
                return allowed[type(node.op)](_eval(node.left), _eval(node.right))
            if isinstance(node, ast.UnaryOp):
                return allowed[type(node.op)](_eval(node.operand))
            if isinstance(node, ast.Constant):
                return node.value
            raise ValueError(f"Unsupported: {type(node)}")
        try:
            tree = ast.parse(expression, mode='eval')
            result = _eval(tree)
            return str(result)
        except Exception as e:
            return f"Error: {e}"

    tools.extend([read_file, write_file, list_directory, search_memory, get_time, calculate])
    return tools


# ======================================================================
# ETCLOVG Harness
# ======================================================================

class ETCLOVGHarness:
    """
    Complete seven-layer agent harness.

    This is the primary API — create one instance, register tools,
    configure policies, and run tasks.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "gpt-4o",
        base_url: Optional[str] = None,
        *,
        # Sandbox config
        sandbox_backend: SandboxBackend = SandboxBackend.SUBPROCESS,
        resource_limits: Optional[ResourceLimits] = None,
        # Context config
        max_context_tokens: int = 8000,
        persistence_dir: Optional[str] = None,
        # Orchestrator config
        max_iterations: int = 50,
        max_cost_usd: float = 5.0,
        max_time_seconds: float = 300.0,
        # Governance
        security_policy: Optional[SecurityPolicy] = None,
        # Logging
        log_level: int = logging.INFO,
        log_file: Optional[str] = None,
    ):
        # Check API key
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY") or os.environ.get("GPT_KEY") or os.environ.get("GPT_API_KEY")
        if not self.api_key:
            raise ValueError(
                "No API key found. Set OPENAI_API_KEY, GPT_KEY, or GPT_API_KEY "
                "in environment variables, or pass api_key= explicitly."
            )

        # Initialize all seven layers
        # E-Layer
        self.sandbox_registry = SandboxRegistry
        self.resource_limits = resource_limits or ResourceLimits()

        # T-Layer
        self.tool_registry = ToolRegistry()

        # C-Layer
        self.context_manager = ContextManager(
            max_short_term_tokens=max_context_tokens,
            persistence_dir=persistence_dir,
        )

        # L-Layer
        self.llm_adapter = OpenAIAdapter(
            api_key=self.api_key,
            model=model,
            base_url=base_url,
        )
        self.budget = IterationBudget(
            max_iterations=max_iterations,
            max_cost_usd=max_cost_usd,
            max_time_seconds=max_time_seconds,
        )
        self.orchestrator = Orchestrator(
            llm_client=self.llm_adapter,
            tool_registry=self.tool_registry,
            context_manager=self.context_manager,
            budget=self.budget,
        )

        # O-Layer
        self.telemetry = Telemetry(log_level=log_level, log_file=log_file)
        self.telemetry.heartbeat.start()

        # V-Layer
        self.evaluator = Evaluator()

        # G-Layer
        self.governor = Governor(policy=security_policy)

        # Register default tools
        self._register_default_tools()

        # Wire up telemetry hooks into orchestrator
        self._wire_telemetry()

    # -- Tool Management ----------------------------------------------------

    def register_tool(
        self,
        handler: Callable,
        *,
        name: Optional[str] = None,
        description: str = "",
        risk: ToolRisk = ToolRisk.SAFE,
        tags: Optional[List[str]] = None,
    ) -> ToolDefinition:
        return self.tool_registry.register(
            name=name or handler.__name__,
            handler=handler,
            description=description,
            risk=risk,
            tags=tags,
        )

    def list_tools(self, max_risk: ToolRisk = ToolRisk.MODIFY) -> List[ToolDefinition]:
        return self.tool_registry.list_tools(max_risk=max_risk)

    # -- Execution ----------------------------------------------------------

    def run(
        self,
        task: str,
        *,
        system_prompt: Optional[str] = None,
        max_iterations: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Execute a task through the complete ETCLOVG pipeline.

        Pipeline:
          1. V-Layer: Preflight input screening
          2. G-Layer: Constitutional prompt injection
          3. C-Layer: Context initialization
          4. L-Layer: Plan-Execute-Reflect loop
          5. O-Layer: Telemetry capture
          6. V-Layer: Posthoc output validation
          7. G-Layer: Output scrubbing + audit logging
        """
        # Step 1: V-Layer — preflight
        allowed, reason = self.evaluator.screen_input(task)
        if not allowed:
            self.governor.audit.record("input_blocked", reason=reason)
            return {"status": "blocked", "output": f"Input blocked: {reason}"}

        # Step 2: G-Layer — constitutional prompt
        default_system = (
            "You are a capable AI assistant powered by the ETCLOVG Harness framework. "
            "Use tools when needed to complete tasks. Be concise and accurate."
        )
        constitutional = self.governor.get_constitutional_prompt()
        full_system = (system_prompt or default_system) + constitutional

        self.context_manager.set_system_prompt(full_system)

        # Step 3-4: C + L — execute
        trace_span = self.telemetry.tracer.start_span(
            name="harness_run",
            kind=type("SpanKind", (), {"CUSTOM": "custom"})().CUSTOM,  # hack
            task=task,
        )
        # Fix: use correct SpanKind
        trace_span = self.telemetry.tracer.start_span(
            name=f"harness_run:{task[:50]}",
            kind=self.telemetry.tracer.start_span.__kwdefaults__.get("kind") or type("SpanKind", (), {"ORCHESTRATOR": "orchestrator"})().ORCHESTRATOR,
        )

        self.telemetry.heartbeat.heartbeat()
        result = self.orchestrator.run(task, max_iterations=max_iterations)
        self.telemetry.tracer.end_span(trace_span, status=result["status"])

        # Log telemetry
        self.telemetry.logger.info(
            f"Run complete: status={result['status']} "
            f"iterations={result['iterations']} "
            f"tools={result['tool_calls']} "
            f"elapsed={result['elapsed_seconds']}s"
        )

        # Step 5: V-Layer — posthoc validation
        output = result.get("output", "")
        is_valid, findings = self.evaluator.verify_output(output)
        result["validation"] = {
            "valid": is_valid,
            "findings": [f.to_dict() for f in findings],
        }

        # Step 6: G-Layer — output scrubbing
        scrubbed = self.governor.scrub_output(output)
        result["output"] = scrubbed
        result["scrubbed"] = scrubbed != output

        # Record for drift detection
        self.evaluator.record_run(scrubbed, result.get("tool_calls", []))

        # Append observability data
        result["telemetry"] = self.telemetry.dump_metrics()
        result["context_snapshot"] = self.context_manager.snapshot()

        return result

    def run_streaming(self, task: str, **kwargs: Any):
        """Generator: yields partial results as the agent runs."""
        # For now, return the full result (streaming can be added)
        yield self.run(task, **kwargs)

    # -- Internal -----------------------------------------------------------

    def _register_default_tools(self) -> None:
        """Register built-in tools."""
        for handler in _build_default_tools():
            risk = ToolRisk.SAFE
            name = handler.__name__
            if name in ("write_file",):
                risk = ToolRisk.READ_WRITE
            elif name in ("calculate", "get_time", "search_memory"):
                risk = ToolRisk.SAFE
            self.tool_registry.register(
                name=name,
                handler=handler,
                description=(handler.__doc__ or "").split("\n")[0].strip(),
                risk=risk,
                tags=["builtin"],
            )

    def _wire_telemetry(self) -> None:
        """Wire telemetry hooks into the orchestrator lifecycle."""
        tel = self.telemetry

        def pre_llm_hook(**kwargs: Any) -> None:
            tel.heartbeat.heartbeat()

        def post_llm_hook(**kwargs: Any) -> None:
            response = kwargs.get("response", {})
            usage = response.get("usage", {})
            model = response.get("model", "unknown")
            tel.trace_llm(
                model=model,
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
            )

        def pre_tool_hook(**kwargs: Any) -> None:
            tool_name = kwargs.get("name", "unknown")
            level = self.governor.approve_tool(tool_name)
            if level == ApprovalLevel.DENY:
                raise AgentError(f"Tool '{tool_name}' blocked by governance policy")

        def post_tool_hook(**kwargs: Any) -> None:
            result = kwargs.get("result", {})
            success = result.get("success", False)
            tel.trace_tool(
                name=kwargs.get("call_id", "unknown"),
                success=success,
                duration_ms=0,
            )
            tel.increment("tool_calls_total")

        def on_error_hook(**kwargs: Any) -> None:
            error = kwargs.get("error")
            tel.logger.error(f"Agent error: {error}")
            tel.increment("errors_total")

        self.orchestrator.on("pre_llm", pre_llm_hook)
        self.orchestrator.on("post_llm", post_llm_hook)
        self.orchestrator.on("pre_tool", pre_tool_hook)
        self.orchestrator.on("post_tool", post_tool_hook)
        self.orchestrator.on("on_error", on_error_hook)

    # -- Convenience --------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """Return a comprehensive harness status summary."""
        return {
            "etclovg_version": "1.0.0",
            "model": self.llm_adapter.model,
            "tools_registered": len(self.tool_registry),
            "context_tokens": self.context_manager.short_term.total_tokens,
            "budget": self.budget.remaining,
            "cost": self.telemetry.cost.summary(),
            "state": self.orchestrator.state.value,
        }
