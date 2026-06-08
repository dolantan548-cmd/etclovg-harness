"""
L-Layer: Lifecycle & Orchestration

Implements the complete Agent lifecycle with four orchestration modes:

  Plan-Execute-Reflect (PER) — the core loop
  ReAct                   — reasoning + acting interleaved
  Multi-Agent             — task delegation across sub-agents
  Streaming Pipeline      — real-time output with tool interrupts

Key innovations from GenericAgent:
  - Budget-driven continuous self-drive (IterationBudget)
  - BBS-style distributed agent coordination via file semaphore
  - Kanban task management with dependency resolution
  - Error classification + intelligent failover (Hermes pattern)
  - Skills system for self-improvement

Key innovations from OpenClaw:
  - Harness plugin architecture replacing the run loop
  - Lane execution channels for parallel isolated execution
  - Execution history replay for debugging
"""

from __future__ import annotations

import time
import json
import enum
import queue
import threading
import traceback
import dataclasses
from typing import Any, Callable, Dict, List, Optional, Tuple, Union
from concurrent.futures import ThreadPoolExecutor, Future
from pathlib import Path


# ======================================================================
# Budget & State
# ======================================================================

class AgentState(enum.Enum):
    IDLE       = "idle"
    RUNNING    = "running"
    WAITING    = "waiting"     # waiting for tool result
    PAUSED     = "paused"
    COMPLETED  = "completed"
    FAILED     = "failed"
    CANCELLED  = "cancelled"


@dataclasses.dataclass
class IterationBudget:
    """Thread-safe iteration budget with auto-stop."""
    max_iterations: int = 50
    max_cost_usd:   float = 5.0
    max_time_seconds: float = 300.0

    _iterations:    int = 0
    _cost_usd:      float = 0.0
    _start_time:    float = dataclasses.field(default_factory=time.time)
    _lock:          threading.Lock = dataclasses.field(default_factory=threading.Lock)

    def consume(self, cost_usd: float = 0.0) -> bool:
        """Return True if budget remains, False if exhausted."""
        with self._lock:
            self._iterations += 1
            self._cost_usd += cost_usd
            elapsed = time.time() - self._start_time
            return (
                self._iterations < self.max_iterations
                and self._cost_usd < self.max_cost_usd
                and elapsed < self.max_time_seconds
            )

    @property
    def remaining(self) -> Dict[str, Any]:
        with self._lock:
            elapsed = time.time() - self._start_time
            return {
                "iterations_left": self.max_iterations - self._iterations,
                "budget_left_usd": round(self.max_cost_usd - self._cost_usd, 4),
                "time_left_seconds": round(self.max_time_seconds - elapsed, 1),
            }

    def reset(self) -> None:
        with self._lock:
            self._iterations = 0
            self._cost_usd = 0.0
            self._start_time = time.time()


# ======================================================================
# Error Classification (Hermes Agent pattern)
# ======================================================================

class ErrorCategory(enum.Enum):
    RETRYABLE     = "retryable"       # transient: rate-limit, timeout
    TOOL_FAILURE  = "tool_failure"    # tool returned error
    MODEL_ERROR   = "model_error"     # LLM API error
    BUDGET_EXCEEDED = "budget_exceeded"
    PERMISSION    = "permission"      # security block
    FATAL         = "fatal"           # unrecoverable


class AgentError(Exception):
    """Classified agent error with category for intelligent failover."""
    def __init__(self, message: str, category: ErrorCategory = ErrorCategory.FATAL):
        super().__init__(message)
        self.category = category
        self.timestamp = time.time()


# ======================================================================
# Task & Kanban
# ======================================================================

@dataclasses.dataclass
class Task:
    id:          str
    description: str
    status:      str = "pending"  # pending | in_progress | completed | failed
    dependencies: List[str] = dataclasses.field(default_factory=list)
    result:      Any = None
    created_at:  float = dataclasses.field(default_factory=time.time)


class KanbanBoard:
    """Simple Kanban task tracker with dependency awareness."""
    def __init__(self):
        self._tasks: Dict[str, Task] = {}
        self._lock = threading.Lock()

    def add(self, task: Task) -> None:
        with self._lock:
            self._tasks[task.id] = task

    def get_ready(self) -> List[Task]:
        with self._lock:
            return [
                t for t in self._tasks.values()
                if t.status == "pending"
                and all(
                    self._tasks.get(d) and self._tasks[d].status == "completed"
                    for d in t.dependencies
                )
            ]

    def update(self, task_id: str, status: str, result: Any = None) -> None:
        with self._lock:
            if task_id in self._tasks:
                self._tasks[task_id].status = status
                if result is not None:
                    self._tasks[task_id].result = result


# ======================================================================
# Core Orchestrator
# ======================================================================

class Orchestrator:
    """
    Agent lifecycle orchestrator implementing Plan-Execute-Reflect.

    Accepts a pluggable LLM client, tool registry, and context manager,
    then drives the core agent loop with budget enforcement and error recovery.
    """

    def __init__(
        self,
        llm_client: Any,        # Provider-agnostic: must have chat(messages, tools) → response
        tool_registry: Any,     # ToolRegistry instance
        context_manager: Any,   # ContextManager instance
        budget: Optional[IterationBudget] = None,
        max_parallel_tools: int = 4,
    ):
        self.llm = llm_client
        self.tools = tool_registry
        self.context = context_manager
        self.budget = budget or IterationBudget()
        self.max_parallel_tools = max_parallel_tools

        self.state = AgentState.IDLE
        self.kanban = KanbanBoard()
        self._executor = ThreadPoolExecutor(max_workers=max_parallel_tools)
        self._event_queue: queue.Queue = queue.Queue()
        self._hooks: Dict[str, List[Callable]] = {
            "pre_llm": [],
            "post_llm": [],
            "pre_tool": [],
            "post_tool": [],
            "on_error": [],
            "on_complete": [],
        }

    # -- Hook System ---------------------------------------------------------

    def on(self, event: str, callback: Callable) -> None:
        if event in self._hooks:
            self._hooks[event].append(callback)

    def _fire(self, event: str, **kwargs: Any) -> None:
        for cb in self._hooks.get(event, []):
            try:
                cb(**kwargs)
            except Exception:
                pass

    # -- Core Loop: Plan-Execute-Reflect -------------------------------------

    def run(self, task: str, max_iterations: Optional[int] = None) -> Dict[str, Any]:
        """
        Execute a task through the Plan-Execute-Reflect loop.

        Returns a result dict with status, output, and telemetry.
        """
        if max_iterations:
            self.budget.max_iterations = max_iterations

        self.state = AgentState.RUNNING
        self.budget.reset()
        start_time = time.time()

        # Phase 1: Plan — inject task into context
        from etclovg.c_layer.memory import Message as Msg
        self.context.add_message(Msg(role="user", content=task))

        final_output = ""
        tool_calls_made = 0
        errors_encountered = 0

        try:
            while self.budget.consume():
                # --- PRE-LLM HOOK ---
                self._fire("pre_llm", state=self.state, budget=self.budget.remaining)

                # Phase 2: Execute — call LLM
                messages = self.context.build_context()
                tool_schemas = self.tools.to_openai_tools()

                try:
                    response = self.llm.chat(messages=messages, tools=tool_schemas or None)
                except Exception as exc:
                    self._handle_error(exc, "llm_call")
                    errors_encountered += 1
                    if errors_encountered > 3:
                        raise AgentError("Too many LLM errors", ErrorCategory.FATAL)
                    continue

                self._fire("post_llm", response=response)

                # Check for tool calls
                tool_calls = response.get("tool_calls", [])
                if tool_calls:
                    # Add assistant message (may contain tool_calls)
                    self.context.add_message(Msg(
                        role="assistant",
                        content=response.get("content", "") or "",
                        tool_calls=tool_calls,
                    ))

                    # Execute tools in parallel
                    tool_futures: Dict[str, Future] = {}
                    for tc in tool_calls:
                        fn_name = tc["function"]["name"]
                        fn_args = json.loads(tc["function"]["arguments"])

                        self._fire("pre_tool", name=fn_name, args=fn_args)
                        future = self._executor.submit(
                            self.tools.invoke_safe, fn_name, fn_args
                        )
                        tool_futures[tc["id"]] = future

                    # Collect results
                    for tc_id, future in tool_futures.items():
                        try:
                            result = future.result(timeout=60)
                        except Exception as exc:
                            result = {"success": False, "error": str(exc)}

                        self._fire("post_tool", call_id=tc_id, result=result)
                        tool_calls_made += 1

                        # Add tool result message
                        self.context.add_message(Msg(
                            role="tool",
                            content=json.dumps(result, ensure_ascii=False)[:4000],
                            tool_call_id=tc_id,
                        ))

                    # Update cost estimate
                    self.budget._cost_usd += len(tool_calls) * 0.002  # rough estimate
                else:
                    # Phase 3: Reflect — final response
                    content = response.get("content", "")
                    final_output = content
                    self.context.add_message(Msg(role="assistant", content=content))
                    break  # Task complete

            self.state = AgentState.COMPLETED

        except AgentError as exc:
            self.state = AgentState.FAILED
            self._fire("on_error", error=exc)
            final_output = f"[FAILED] {exc}"

        except Exception as exc:
            self.state = AgentState.FAILED
            self._fire("on_error", error=exc)
            final_output = f"[ERROR] {exc}"

        elapsed = time.time() - start_time

        result = {
            "status": self.state.value,
            "output": final_output,
            "iterations": self.budget._iterations,
            "tool_calls": tool_calls_made,
            "errors": errors_encountered,
            "elapsed_seconds": round(elapsed, 2),
            "cost_estimate_usd": round(self.budget._cost_usd, 4),
        }

        self._fire("on_complete", result=result)
        return result

    # -- Multi-Agent Delegation -----------------------------------------------

    def delegate(self, sub_task: str, agent_fn: Callable[[str], Dict[str, Any]]) -> Dict[str, Any]:
        """Delegate a sub-task to another agent instance."""
        task_id = f"delegate-{time.time_ns()}"
        task = Task(id=task_id, description=sub_task)
        self.kanban.add(task)
        self.kanban.update(task_id, "in_progress")

        try:
            result = agent_fn(sub_task)
            self.kanban.update(task_id, "completed", result)
            return result
        except Exception as exc:
            self.kanban.update(task_id, "failed", str(exc))
            raise

    # -- Helpers --------------------------------------------------------------

    def _handle_error(self, exc: Exception, context: str) -> None:
        category = ErrorCategory.RETRYABLE if isinstance(exc, (TimeoutError, ConnectionError)) else ErrorCategory.FATAL
        agent_err = AgentError(f"[{context}] {exc}", category)
        self._fire("on_error", error=agent_err)

    def stop(self) -> None:
        self.state = AgentState.CANCELLED
        self._executor.shutdown(wait=False)

    def __del__(self) -> None:
        try:
            self._executor.shutdown(wait=False)
        except Exception:
            pass
