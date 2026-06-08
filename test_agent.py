"""
Test suite for ETCLOVG Harness.

Run with: python test_agent.py
"""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from etclovg import ETCLOVGHarness, __version__
from etclovg.e_layer.sandbox import SandboxRegistry, SandboxBackend, ResourceLimits
from etclovg.t_layer.registry import ToolRegistry, ToolRisk
from etclovg.c_layer.memory import ContextManager, Message
from etclovg.l_layer.orchestrator import Orchestrator, IterationBudget, AgentState
from etclovg.o_layer.telemetry import Telemetry
from etclovg.v_layer.evaluator import Evaluator, TestCase, TestResult
from etclovg.g_layer.governor import (
    Governor, SecurityPolicy, ApprovalLevel, ToolRiskCategory, PIIScrubber, AuditTrail,
)


# =========================== Unit Tests ===========================

def test_e_layer() -> None:
    """E-Layer: Sandbox registry and subprocess sandbox."""
    print("[E-Layer] Testing sandbox registry...")
    assert SandboxRegistry is not None
    limits = ResourceLimits(max_time_seconds=5, max_memory_mb=256)
    sandbox = SandboxRegistry.create(SandboxBackend.SUBPROCESS, limits=limits)
    result = sandbox.run("echo hello")
    assert result.success
    assert "hello" in result.stdout
    print("  PASS")


def test_t_layer() -> None:
    """T-Layer: Tool registry with risk classification."""
    print("[T-Layer] Testing tool registry...")
    registry = ToolRegistry()

    def dummy_search(query: str) -> str:
        """Search for a query."""  # noqa: D401
        return f"Results for {query}"
    registry.register("search", dummy_search, description="Web search", risk=ToolRisk.NETWORK)

    tool_def = registry.get("search")
    assert tool_def is not None
    assert tool_def.risk == ToolRisk.NETWORK

    openai_schema = tool_def.to_openai_schema()
    assert openai_schema["type"] == "function"
    print("  PASS")


def test_c_layer() -> None:
    """C-Layer: Three-tier memory and incremental compression."""
    print("[C-Layer] Testing context manager...")
    cm = ContextManager(max_short_term_tokens=2000)

    cm.set_system_prompt("You are a helpful assistant.")
    cm.add_user_message("Hello")
    cm.add_assistant_message("Hi there!")

    snapshot = cm.snapshot()
    assert snapshot["messages_count"] == 3
    assert snapshot["total_tokens"] > 0
    print("  PASS")


def test_l_layer() -> None:
    """L-Layer: Budget and orchestrator lifecycle."""
    print("[L-Layer] Testing orchestrator budget...")
    budget = IterationBudget(max_iterations=10, max_cost_usd=0.50, max_time_seconds=30)
    assert budget.iterate()  # Should be allowed
    assert budget.remaining["iterations"] == 9
    print("  PASS")


def test_o_layer() -> None:
    """O-Layer: Telemetry, cost tracking, heartbeat."""
    print("[O-Layer] Testing telemetry...")
    tel = Telemetry()

    tel.trace_tool("test_tool", success=True, duration_ms=150)
    assert tel.get_counter("tool_calls_total") == 1

    tel.trace_llm("gpt-4o", input_tokens=100, output_tokens=50)
    cost_summary = tel.cost.summary()
    assert cost_summary["total_calls"] == 1
    assert cost_summary["total_input_tokens"] == 100

    tel.heartbeat.start()
    assert tel.heartbeat.is_alive()
    tel.heartbeat.stop()
    print("  PASS")


def test_v_layer() -> None:
    """V-Layer: Preflight validation, posthoc verification."""
    print("[V-Layer] Testing evaluator...")
    evaluator = Evaluator()

    # Preflight
    allowed, _ = evaluator.screen_input("Harmless question")
    assert allowed

    blocked, reason = evaluator.screen_input("rm -rf / --no-preserve-root")
    assert blocked

    # Posthoc
    valid, findings = evaluator.verify_output("The answer is 42.")
    assert valid is not None
    print("  PASS")


def test_g_layer() -> None:
    """G-Layer: Governance, approval, PII scrubbing, audit."""
    print("[G-Layer] Testing governor...")

    policy = SecurityPolicy(denied_tools={"rm_rf"})
    governor = Governor(policy=policy)

    # Tool approval
    level = governor.approve_tool("rm_rf", "Dangerous system tool")
    assert level == ApprovalLevel.DENY

    level = governor.approve_tool("read_file", "Read a file")
    assert level == ApprovalLevel.AUTO

    # PII scrubbing
    text = "Contact user@example.com or call 123-456-7890"
    cleaned, count = governor.pii_scrubber.scrub(text)
    assert count >= 2
    assert "user@example.com" not in cleaned
    assert "[REDACTED_EMAIL]" in cleaned

    # Audit trail
    governor.audit.record("test_event", key="value")
    entries = governor.audit.query(event="test_event")
    assert len(entries) == 1

    print("  PASS")


def test_harness_integration() -> None:
    """Integration: Full harness construction without LLM call."""
    print("[Integration] Testing harness construction...")

    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("GPT_KEY") or "sk-test"
    if api_key == "sk-test":
        os.environ["OPENAI_API_KEY"] = "sk-test-dummy"

    harness = ETCLOVGHarness(api_key="sk-test-dummy", model="gpt-4o-mini")
    assert harness.tool_registry is not None
    assert harness.context_manager is not None
    assert harness.governor is not None

    summary = harness.summary()
    assert summary["etclovg_version"] == "1.0.0"
    assert summary["tools_registered"] >= 5
    print("  PASS")


# =========================== Main ===========================

if __name__ == "__main__":
    print(f"\n  ETCLOVG Harness v{__version__} — Unit Test Suite\n")

    tests = [
        test_e_layer, test_t_layer, test_c_layer,
        test_l_layer, test_o_layer, test_v_layer,
        test_g_layer, test_harness_integration,
    ]

    passed = 0
    failed = 0
    for test in tests:
        try:
            test()
            passed += 1
        except Exception as e:
            print(f"  FAIL: {e}")
            import traceback
            traceback.print_exc()
            failed += 1

    print(f"\n  Results: {passed}/{len(tests)} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
