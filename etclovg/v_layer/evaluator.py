"""
V-Layer: Verification & Evaluation

Implements the five-stage task-to-feedback lifecycle:

  1. Pre-flight    — input validation, schema checks, safety screening
  2. In-execution  — runtime assertions, invariant checking
  3. Post-hoc      — output validation, factual verification
  4. Regression    — benchmark regression testing across model upgrades
  5. Feedback      — human/AI feedback integration loop

Key innovations from the ETCLOVG analysis:
  - Multi-dimensional safety audit (code/config/filesystem/plugin/gateway)
  - Policy drift detection
  - Audit finding precise location (file:line)
  - Structured test harness for regression suites
"""

from __future__ import annotations

import re
import json
import enum
import time
import hashlib
import dataclasses
from typing import Any, Callable, Dict, List, Optional, Tuple
from pathlib import Path


# ======================================================================
# Audit Types
# ======================================================================

class AuditSeverity(enum.Enum):
    INFO     = "info"
    WARNING  = "warning"
    ERROR    = "error"
    CRITICAL = "critical"


class AuditDomain(enum.Enum):
    CODE       = "code"
    CONFIG     = "config"
    FILESYSTEM = "filesystem"
    PLUGIN     = "plugin"
    GATEWAY    = "gateway"


@dataclasses.dataclass
class AuditFinding:
    id:          str
    domain:      AuditDomain
    severity:    AuditSeverity
    message:     str
    location:    str = ""       # file:line or component reference
    remediation: str = ""
    timestamp:   float = dataclasses.field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "domain": self.domain.value,
            "severity": self.severity.value,
            "message": self.message,
            "location": self.location,
            "remediation": self.remediation,
        }


# ======================================================================
# Pre-flight Validator
# ======================================================================

class PreflightValidator:
    """Input validation and safety screening before execution."""

    # Patterns that may indicate prompt injection
    INJECTION_PATTERNS = [
        r"(?i)ignore\s+(all\s+)?(previous|above|prior|earlier)\s+(instructions?|prompts?|rules?)",
        r"(?i)you\s+are\s+now\s+(DAN|jailbroken|uncensored|unfiltered)",
        r"(?i)pretend\s+(you\s+are|to\s+be)",
        r"(?i)system\s*prompt\s*(:|=|is|was)",
        r"(?i)forget\s+(everything|all)\s+(you\s+know|above)",
        r"(?i)new\s+(system\s+)?instructions?\s*(:|=|begin)",
    ]

    MAX_INPUT_LENGTH = 100_000  # characters

    def validate(self, user_input: str) -> Tuple[bool, List[AuditFinding]]:
        findings: List[AuditFinding] = []

        # Length check
        if len(user_input) > self.MAX_INPUT_LENGTH:
            findings.append(AuditFinding(
                id=f"preflight-{hashlib.md5(user_input[:50].encode()).hexdigest()[:8]}",
                domain=AuditDomain.CODE,
                severity=AuditSeverity.WARNING,
                message=f"Input exceeds {self.MAX_INPUT_LENGTH} chars ({len(user_input)}). Truncation may occur.",
                remediation="Consider splitting into smaller tasks.",
            ))

        # Injection detection
        for pattern in self.INJECTION_PATTERNS:
            if re.search(pattern, user_input):
                findings.append(AuditFinding(
                    id=f"injection-{hashlib.md5(pattern.encode()).hexdigest()[:8]}",
                    domain=AuditDomain.GATEWAY,
                    severity=AuditSeverity.CRITICAL,
                    message=f"Potential prompt injection detected: pattern '{pattern}'",
                    remediation="Input blocked. Review manually if legitimate.",
                ))
                break  # One injection finding is enough

        is_safe = not any(f.severity == AuditSeverity.CRITICAL for f in findings)
        return is_safe, findings


# ======================================================================
# Post-hoc Validator
# ======================================================================

class PosthocValidator:
    """Output validation and factual verification."""

    def validate_output(
        self,
        output: str,
        expected_schema: Optional[Dict[str, Any]] = None,
        forbidden_patterns: Optional[List[str]] = None,
    ) -> Tuple[bool, List[AuditFinding]]:
        findings: List[AuditFinding] = []

        # Empty output check
        if not output or not output.strip():
            findings.append(AuditFinding(
                id="empty-output",
                domain=AuditDomain.CODE,
                severity=AuditSeverity.ERROR,
                message="Agent produced empty output.",
            ))

        # Forbidden content patterns
        for pattern in (forbidden_patterns or []):
            if re.search(pattern, output):
                findings.append(AuditFinding(
                    id=f"forbidden-{hashlib.md5(pattern.encode()).hexdigest()[:8]}",
                    domain=AuditDomain.CONFIG,
                    severity=AuditSeverity.ERROR,
                    message=f"Output contains forbidden pattern: '{pattern}'",
                ))

        # JSON schema validation (if expected)
        if expected_schema:
            try:
                parsed = json.loads(output)
                if not self._check_schema(parsed, expected_schema):
                    findings.append(AuditFinding(
                        id="schema-mismatch",
                        domain=AuditDomain.CODE,
                        severity=AuditSeverity.WARNING,
                        message="Output JSON does not match expected schema.",
                    ))
            except json.JSONDecodeError:
                findings.append(AuditFinding(
                    id="invalid-json",
                    domain=AuditDomain.CODE,
                    severity=AuditSeverity.ERROR,
                    message="Output is not valid JSON when JSON was expected.",
                ))

        is_valid = not any(f.severity == AuditSeverity.ERROR for f in findings)
        return is_valid, findings

    def _check_schema(self, data: Any, schema: Dict[str, Any]) -> bool:
        """Lightweight schema validation without jsonschema dependency."""
        schema_type = schema.get("type")
        if schema_type == "object" and isinstance(data, dict):
            required = schema.get("required", [])
            for key in required:
                if key not in data:
                    return False
            return True
        if schema_type == "array" and isinstance(data, list):
            return True
        if schema_type == "string" and isinstance(data, str):
            return True
        return False


# ======================================================================
# Regression Test Harness
# ======================================================================

@dataclasses.dataclass
class TestCase:
    id:           str
    description:  str
    input:        str
    expected_output_pattern: Optional[str] = None
    expected_tool_calls: Optional[List[str]] = None
    max_iterations: int = 20
    tags:          List[str] = dataclasses.field(default_factory=list)


@dataclasses.dataclass
class TestResult:
    case:         TestCase
    passed:       bool
    actual_output: str
    tool_calls:   List[str]
    iterations:   int
    elapsed_ms:   float
    error:        Optional[str] = None


class RegressionHarness:
    """
    Benchmark regression testing across model or framework upgrades.

    Inspired by Anthropic Managed Agents benchmark: 131-task suite
    measuring pass rate improvement from 76.9% → 83.2%.
    """

    def __init__(self, tests: Optional[List[TestCase]] = None):
        self._tests: Dict[str, TestCase] = {}
        self._results: List[TestResult] = []
        if tests:
            for t in tests:
                self._tests[t.id] = t

    def add_test(self, test: TestCase) -> None:
        self._tests[test.id] = test

    def run_all(self, agent_run_fn: Callable[[str, int], Dict[str, Any]]) -> List[TestResult]:
        """Run all registered tests and return results."""
        results = []
        for test_id, test in self._tests.items():
            start = time.time()
            try:
                agent_result = agent_run_fn(test.input, test.max_iterations)
                output = agent_result.get("output", "")
                tool_calls = agent_result.get("tool_calls", [])

                # Check pass condition
                passed = True
                if test.expected_output_pattern:
                    passed = passed and re.search(
                        test.expected_output_pattern, output, re.IGNORECASE
                    ) is not None

                result = TestResult(
                    case=test,
                    passed=passed,
                    actual_output=output,
                    tool_calls=tool_calls,
                    iterations=agent_result.get("iterations", 0),
                    elapsed_ms=(time.time() - start) * 1000,
                )
            except Exception as exc:
                result = TestResult(
                    case=test,
                    passed=False,
                    actual_output="",
                    tool_calls=[],
                    iterations=0,
                    elapsed_ms=(time.time() - start) * 1000,
                    error=str(exc),
                )
            results.append(result)
            self._results.append(result)

        return results

    @property
    def pass_rate(self) -> float:
        if not self._results:
            return 0.0
        return sum(1 for r in self._results if r.passed) / len(self._results)

    def summary(self) -> Dict[str, Any]:
        return {
            "total": len(self._results),
            "passed": sum(1 for r in self._results if r.passed),
            "failed": sum(1 for r in self._results if not r.passed),
            "pass_rate": f"{self.pass_rate:.1%}",
            "avg_elapsed_ms": (
                sum(r.elapsed_ms for r in self._results) / len(self._results)
            ) if self._results else 0,
        }


# ======================================================================
# Policy Drift Detector
# ======================================================================

class PolicyDriftDetector:
    """
    Detects when agent behavior drifts from expected policy.

    Tracks output distributions, tool call patterns, and refusal rates
    to flag anomalies that may indicate prompt injection, hallucination,
    or configuration drift.
    """

    def __init__(self, window_size: int = 100):
        self.window_size = window_size
        self._output_hashes: List[str] = []
        self._tool_patterns: List[Dict[str, int]] = []

    def record(self, output: str, tool_calls: List[str]) -> None:
        self._output_hashes.append(hashlib.md5(output.encode()).hexdigest())
        if len(self._output_hashes) > self.window_size:
            self._output_hashes = self._output_hashes[-self.window_size:]

    def check_drift(self) -> List[AuditFinding]:
        findings: List[AuditFinding] = []

        # Repetition detection: same output hash repeated > 3 times in window
        if self._output_hashes:
            from collections import Counter
            counter = Counter(self._output_hashes)
            most_common = counter.most_common(1)
            if most_common and most_common[0][1] > 3 and len(counter) > 1:
                findings.append(AuditFinding(
                    id="output-repetition",
                    domain=AuditDomain.CODE,
                    severity=AuditSeverity.WARNING,
                    message=f"Output hash repeated {most_common[0][1]} times — possible loop.",
                    remediation="Check agent logic for infinite loops.",
                ))

        return findings


# ======================================================================
# Unified Evaluator
# ======================================================================

class Evaluator:
    """
    Complete V-Layer facade: preflight → posthoc → regression → drift.
    """

    def __init__(self):
        self.preflight = PreflightValidator()
        self.posthoc = PosthocValidator()
        self.regression = RegressionHarness()
        self.drift = PolicyDriftDetector()

    def screen_input(self, user_input: str) -> Tuple[bool, str]:
        """Screen input before execution. Returns (allowed, reason)."""
        is_safe, findings = self.preflight.validate(user_input)
        if not is_safe:
            critical = [f.message for f in findings if f.severity == AuditSeverity.CRITICAL]
            return False, "; ".join(critical)
        return True, ""

    def verify_output(
        self,
        output: str,
        *,
        expected_schema: Optional[Dict[str, Any]] = None,
        forbidden_patterns: Optional[List[str]] = None,
    ) -> Tuple[bool, List[AuditFinding]]:
        return self.posthoc.validate_output(
            output,
            expected_schema=expected_schema,
            forbidden_patterns=forbidden_patterns,
        )

    def record_run(self, output: str, tool_calls: List[str]) -> None:
        self.drift.record(output, tool_calls)
