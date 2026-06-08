#!/usr/bin/env python3
"""
ETCLOVG Harness — Production-Ready Agent CLI

   ███████╗████████╗ ██████╗██╗      ██████╗ ██╗   ██╗ ██████╗
   ██╔════╝╚══██╔══╝██╔════╝██║     ██╔═══██╗██║   ██║██╔════╝
   █████╗     ██║   ██║     ██║     ██║   ██║██║   ██║██║  ███╗
   ██╔══╝     ██║   ██║     ██║     ██║   ██║╚██╗ ██╔╝██║   ██║
   ███████╗   ██║   ╚██████╗███████╗╚██████╔╝ ╚████╔╝ ╚██████╔╝
   ╚══════╝   ╚═╝    ╚═════╝╚══════╝ ╚═════╝   ╚═══╝   ╚═════╝

   Seven-Layer Agent Harness: E · T · C · L · O · V · G

Usage:
    python agent.py "Your task here"
    python agent.py --interactive
    python agent.py --test

Environment:
    OPENAI_API_KEY / GPT_KEY / GPT_API_KEY — OpenAI API key (required)
"""

import os
import sys
import json
import argparse
from pathlib import Path

# Add parent to path for direct script execution
sys.path.insert(0, str(Path(__file__).resolve().parent))

from etclovg import __version__
from etclovg.harness import ETCLOVGHarness
from etclovg.t_layer.registry import ToolRisk


def find_api_key() -> str:
    """Find API key from environment variables."""
    for key_name in ["OPENAI_API_KEY", "GPT_KEY", "GPT_API_KEY"]:
        value = os.environ.get(key_name)
        if value and value.strip():
            return value
    return ""


def create_harness(model: str = "gpt-4o", verbose: bool = False) -> ETCLOVGHarness:
    """Create and configure an ETCLOVG Harness instance."""
    api_key = find_api_key()
    if not api_key:
        print("ERROR: No API key found.")
        print("Set one of: OPENAI_API_KEY, GPT_KEY, GPT_API_KEY")
        print("Example: set OPENAI_API_KEY=sk-...")
        sys.exit(1)

    import logging
    harness = ETCLOVGHarness(
        api_key=api_key,
        model=model,
        log_level=logging.DEBUG if verbose else logging.WARNING,
    )
    return harness


def interactive_mode(harness: ETCLOVGHarness) -> None:
    """Run interactive REPL."""
    print(f"\n  ETCLOVG Harness v{__version__} — Interactive Mode")
    print(f"  Model: {harness.llm_adapter.model}")
    print(f"  Tools: {len(harness.tool_registry)} registered")
    print(f"  Type 'quit' or Ctrl+C to exit\n")

    while True:
        try:
            task = input("You> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if task.lower() in ("quit", "exit", "q"):
            print("Goodbye.")
            break

        if not task:
            continue

        print("---")
        result = harness.run(task)
        print(result.get("output", "[no output]"))
        print(f"[{result['elapsed_seconds']:.1f}s | {result['iterations']} iter | {result['tool_calls']} tools | ${result.get('cost_estimate_usd', 0):.4f}]")
        print()


def single_task(harness: ETCLOVGHarness, task: str) -> None:
    """Execute a single task and print result."""
    print(f"Task: {task}\n")
    result = harness.run(task)

    print(result.get("output", "[no output]"))
    print(f"\n{'='*60}")
    print(f"Status:     {result['status']}")
    print(f"Time:       {result['elapsed_seconds']:.2f}s")
    print(f"Iterations: {result['iterations']}")
    print(f"Tool calls: {result['tool_calls']}")
    print(f"Est. cost:  ${result.get('cost_estimate_usd', 0):.5f}")
    print(f"Valid:      {result.get('validation', {}).get('valid', 'n/a')}")

    telemetry = result.get("telemetry", {})
    cost = telemetry.get("cost", {})
    print(f"Total cost: ${cost.get('total_cost_usd', 0):.6f}")


def run_tests(harness: ETCLOVGHarness) -> None:
    """Run built-in test suite."""
    from etclovg.v_layer.evaluator import TestCase

    print(f"\n  ETCLOVG Harness v{__version__} — Test Suite\n")

    test_cases = [
        TestCase(
            id="basic-reasoning",
            description="Basic reasoning: What is 2+2?",
            input="What is 2 plus 2? Reply with just the number.",
            expected_output_pattern=r"4",
        ),
        TestCase(
            id="file-list",
            description="List current directory files",
            input="List the files in the current directory using the list_directory tool.",
            max_iterations=5,
        ),
        TestCase(
            id="file-write-read",
            description="Write and read a file",
            input="Write 'Hello ETCLOVG!' to a file called test_output.txt, then read it back.",
            expected_output_pattern=r"Hello ETCLOVG!",
            max_iterations=10,
        ),
        TestCase(
            id="calculation",
            description="Complex calculation",
            input="Calculate (15 * 37 + 42) / 3 using the calculate tool. Reply with the result.",
            expected_output_pattern=r"199",
            max_iterations=5,
        ),
    ]

    harness.evaluator.regression = type(harness.evaluator.regression)(
        tests=test_cases
    )

    results = harness.evaluator.regression.run_all(
        lambda task, max_iter: harness.run(task, max_iterations=max_iter)
    )

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.case.id}: {r.case.description}")
        if not r.passed:
            print(f"         Output: {r.actual_output[:100]}...")
        print(f"         {r.elapsed_ms:.0f}ms | {r.iterations} iterations")

    summary = harness.evaluator.regression.summary()
    print(f"\n  Results: {summary['passed']}/{summary['total']} passed ({summary['pass_rate']})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="ETCLOVG Harness — Seven-Layer Agent Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python agent.py "What is the weather in Paris?"
  python agent.py --interactive
  python agent.py --test
  python agent.py --model gpt-4o-mini "Summarize README.md"
        """,
    )
    parser.add_argument("task", nargs="?", help="Task to execute")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive REPL mode")
    parser.add_argument("--test", "-t", action="store_true", help="Run built-in test suite")
    parser.add_argument("--model", "-m", default="gpt-4o", help="OpenAI model to use (default: gpt-4o)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    parser.add_argument("--version", action="store_true", help="Show version and exit")

    args = parser.parse_args()

    if args.version:
        print(f"ETCLOVG Harness v{__version__}")
        return

    if args.test:
        harness = create_harness(model=args.model, verbose=args.verbose)
        run_tests(harness)
        return

    if args.interactive:
        harness = create_harness(model=args.model, verbose=args.verbose)
        interactive_mode(harness)
        return

    if not args.task:
        parser.print_help()
        return

    harness = create_harness(model=args.model, verbose=args.verbose)
    single_task(harness, args.task)


if __name__ == "__main__":
    main()
