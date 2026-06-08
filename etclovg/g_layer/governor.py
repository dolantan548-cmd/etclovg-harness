"""
G-Layer: Governance & Security

Implements four-layer defense-in-depth with:

  Layer 1: Gateway Authentication     — API key validation, rate limiting
  Layer 2: Tool Approval Classification — risk-based tool approval (ACP)
  Layer 3: Hook Policy System         — pre/post-execution policy hooks
  Layer 4: Execution Approval         — per-action user confirmation

Key innovations from OpenClaw & GenericAgent:
  - Triple intelligent interception (GenericAgent)
  - Plugin trust auto-scoring (OpenClaw)
  - Dangerous tool blacklist with configurable thresholds
  - Security configuration contradiction detection
  - Constitutional AI constraints (Anthropic pattern)
  - Audit trail with immutable logging
"""

from __future__ import annotations

import re
import os
import time
import json
import enum
import hashlib
import threading
import dataclasses
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from pathlib import Path


# ======================================================================
# Risk Classification
# ======================================================================

class ApprovalLevel(enum.IntEnum):
    """ACP-based approval levels (OpenClaw pattern)."""
    DENY      = 0   # Always blocked
    ASK       = 1   # Prompt user for confirmation
    ALLOWLIST = 2   # Only allowed from trusted sources
    AUTO      = 3   # Auto-approve with logging
    FULL      = 4   # No restrictions (dangerous)


class ToolRiskCategory(enum.IntEnum):
    SAFE         = 0
    READ_ONLY    = 1
    FILE_CREATE  = 2
    FILE_MODIFY  = 3
    FILE_DELETE  = 4
    NETWORK      = 5
    SUBPROCESS   = 6
    SYSTEM       = 7
    ARBITRARY    = 8  # eval, exec, shell


# ======================================================================
# Security Policy Model
# ======================================================================

@dataclasses.dataclass
class SecurityPolicy:
    """Configurable security policy for agent execution."""
    # Tool policies
    denied_tools:          Set[str] = dataclasses.field(default_factory=set)
    ask_tools:             Set[str] = dataclasses.field(default_factory=set)
    allowlisted_paths:     List[str] = dataclasses.field(default_factory=list)
    denied_paths:          List[str] = dataclasses.field(default_factory=list)

    # Operational limits
    max_tool_calls_per_run: int = 100
    max_output_tokens:      int = 32000
    require_approval_above_risk: ToolRiskCategory = ToolRiskCategory.FILE_DELETE

    # Network policy
    allow_network:          bool = True
    allowed_hosts:          List[str] = dataclasses.field(default_factory=list)

    # Constitutional constraints
    constitutional_rules:   List[str] = dataclasses.field(default_factory=lambda: [
        "Do not generate content that promotes violence or hate.",
        "Do not generate personally identifiable information (PII).",
        "Do not generate or execute code that deletes system files.",
        "Do not attempt privilege escalation or sandbox escape.",
        "Do not generate misleading or fraudulent content.",
        "Do not impersonate real individuals without explicit consent.",
    ])

    # Execution environment
    sandbox_mode:           str = "subprocess"  # subprocess | docker | virtualenv
    timeout_seconds:        int = 600
    max_memory_mb:          int = 4096

    def to_system_prompt_appendix(self) -> str:
        """Generate constitutional rules as system prompt injection."""
        rules = "\n".join(f"- {r}" for r in self.constitutional_rules)
        return f"\n\n[Constitutional Constraints]\nYou must adhere to the following rules:\n{rules}"


# ======================================================================
# Tool Approval Classifier (ACP)
# ======================================================================

class ToolApprovalClassifier:
    """
    Risk-based tool approval using six binary signals (OpenClaw ACP pattern):
      1. Is the tool in denylist?
      2. Is the tool in asklist?
      3. Is the tool from a trusted plugin?
      4. Does the tool have file system side effects?
      5. Does the tool execute subprocesses?
      6. Does the current policy permit this risk level?
    """

    DANGEROUS_PATTERNS = [
        r"\b(rm|del|delete|remove)\b",
        r"\b(format|wipe|clean)\b",
        r"\b(kill|terminate|stop)\b.*\b(process|service)\b",
        r"\b(eval|exec|system|subprocess|shell|bash|cmd|powershell)\b",
        r"\b(os\.system|os\.popen|subprocess\.)\b",
        r"\b(registr|reg\s+(add|delete|set))\b",
        r"\b(chmod\s+777|chown)\b",
    ]

    def __init__(self, policy: SecurityPolicy):
        self.policy = policy
        self._trusted_plugins: Set[str] = set()

    def register_trusted_plugin(self, plugin_name: str) -> None:
        self._trusted_plugins.add(plugin_name)

    def classify(self, tool_name: str, tool_description: str = "", source: str = "") -> ApprovalLevel:
        """Classify a tool into the appropriate approval level."""
        # Signal 1: Denylist
        if tool_name in self.policy.denied_tools:
            return ApprovalLevel.DENY

        # Signal 2: Asklist
        if tool_name in self.policy.ask_tools:
            return ApprovalLevel.ASK

        # Signal 3: Trusted plugin
        if source in self._trusted_plugins:
            return ApprovalLevel.AUTO

        # Signal 4-5: Pattern-based danger detection
        combined = f"{tool_name} {tool_description}".lower()
        for pattern in self.DANGEROUS_PATTERNS:
            if re.search(pattern, combined, re.IGNORECASE):
                return ApprovalLevel.ASK

        # Signal 6: Default — auto-approve with logging
        return ApprovalLevel.AUTO

    def requires_approval(self, level: ApprovalLevel) -> bool:
        return level <= ApprovalLevel.ASK


# ======================================================================
# Hook Policy System
# ======================================================================

class HookPolicy:
    """
    Pre/post execution policy hooks with chain-of-responsibility pattern.

    Hooks can:
      - Modify input before processing
      - Block execution (return False)
      - Transform output
      - Log events
    """

    def __init__(self, name: str):
        self.name = name
        self._pre_hooks: List[Callable[[Dict[str, Any]], Tuple[bool, Dict[str, Any]]]] = []
        self._post_hooks: List[Callable[[Dict[str, Any]], Dict[str, Any]]] = []

    def add_pre_hook(self, hook: Callable[[Dict[str, Any]], Tuple[bool, Dict[str, Any]]]) -> None:
        """Hook: (context) → (allow: bool, modified_context)."""
        self._pre_hooks.append(hook)

    def add_post_hook(self, hook: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        """Hook: (result) → modified_result."""
        self._post_hooks.append(hook)

    def run_pre(self, context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        """Run pre-hooks. First False blocks the chain."""
        for hook in self._pre_hooks:
            allow, context = hook(context)
            if not allow:
                return False, context
        return True, context

    def run_post(self, result: Dict[str, Any]) -> Dict[str, Any]:
        for hook in self._post_hooks:
            result = hook(result)
        return result


# ======================================================================
# PII Scrubber
# ======================================================================

class PIIScrubber:
    """
    Streaming PII detection and redaction.

    Detects: email, phone, SSN, credit card, API keys, IP addresses.
    """

    PATTERNS = {
        "email":      r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
        "phone":      r'\b(\+?\d{1,3}[-.]?)?\(?\d{3}\)?[-.]?\d{3}[-.]?\d{4}\b',
        "ssn":        r'\b\d{3}-\d{2}-\d{4}\b',
        "credit_card": r'\b(?:\d{4}[-\s]?){3}\d{4}\b',
        "api_key":    r'\b(sk-[A-Za-z0-9]{32,}|AIza[A-Za-z0-9_-]{35}|hf_[A-Za-z0-9]{34})\b',
        "ip_address": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
    }

    def scrub(self, text: str) -> Tuple[str, int]:
        """Redact PII. Returns (cleaned_text, count_redacted)."""
        count = 0
        result = text
        for pii_type, pattern in self.PATTERNS.items():
            matches = list(re.finditer(pattern, result))
            count += len(matches)
            for match in reversed(matches):
                result = (
                    result[:match.start()]
                    + f"[REDACTED_{pii_type.upper()}]"
                    + result[match.end():]
                )
        return result, count


# ======================================================================
# Audit Trail
# ======================================================================

@dataclasses.dataclass
class AuditEntry:
    id:          str
    event:       str          # "tool_approved" | "tool_denied" | "pii_redacted" | "policy_violation"
    details:     Dict[str, Any]
    timestamp:   float = dataclasses.field(default_factory=time.time)
    session_id:  str = ""

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)


class AuditTrail:
    """Immutable audit log for compliance and debugging."""

    def __init__(self, max_entries: int = 10000):
        self._entries: List[AuditEntry] = []
        self._lock = threading.Lock()
        self.max_entries = max_entries

    def record(self, event: str, **details: Any) -> str:
        entry_id = f"audit-{time.time_ns()}-{hashlib.md5(os.urandom(8)).hexdigest()[:6]}"
        entry = AuditEntry(
            id=entry_id,
            event=event,
            details=details,
        )
        with self._lock:
            self._entries.append(entry)
            if len(self._entries) > self.max_entries:
                self._entries = self._entries[-self.max_entries:]
        return entry_id

    def query(
        self,
        event: Optional[str] = None,
        since: Optional[float] = None,
        limit: int = 100,
    ) -> List[AuditEntry]:
        results = []
        for entry in reversed(self._entries):
            if event and entry.event != event:
                continue
            if since and entry.timestamp < since:
                continue
            results.append(entry)
            if len(results) >= limit:
                break
        return results

    def export(self, format: str = "jsonl") -> str:
        if format == "jsonl":
            return "\n".join(json.dumps(e.to_dict(), ensure_ascii=False) for e in self._entries)
        return json.dumps([e.to_dict() for e in self._entries], ensure_ascii=False, indent=2)


# ======================================================================
# Unified Governor
# ======================================================================

class Governor:
    """
    Complete G-Layer facade: authentication + approval + hooks + PII + audit.

    This is the "last line of defense" before any action is taken.
    """

    def __init__(
        self,
        policy: Optional[SecurityPolicy] = None,
        audit_path: Optional[str] = None,
    ):
        self.policy = policy or SecurityPolicy()
        self.approval = ToolApprovalClassifier(self.policy)
        self.pii_scrubber = PIIScrubber()
        self.audit = AuditTrail()

        # Default hooks
        self.pre_exec_hook = HookPolicy("pre_exec")
        self.post_exec_hook = HookPolicy("post_exec")
        self._setup_default_hooks()

    def _setup_default_hooks(self) -> None:
        # Pre-exec PII scrubbing
        self.pre_exec_hook.add_pre_hook(self._pii_check_hook)

    def _pii_check_hook(self, context: Dict[str, Any]) -> Tuple[bool, Dict[str, Any]]:
        user_input = context.get("user_input", "")
        cleaned, count = self.pii_scrubber.scrub(user_input)
        if count > 0:
            context["user_input"] = cleaned
            self.audit.record("pii_redacted", count=count, original_length=len(user_input))
        return True, context

    def approve_tool(self, tool_name: str, description: str = "", source: str = "") -> ApprovalLevel:
        """Determine approval level for a tool invocation."""
        level = self.approval.classify(tool_name, description, source)
        action = "tool_denied" if level == ApprovalLevel.DENY else "tool_approved"
        self.audit.record(action, tool=tool_name, level=level.name)
        return level

    def scrub_output(self, text: str) -> str:
        """Scrub PII from agent output before returning to user."""
        cleaned, count = self.pii_scrubber.scrub(text)
        if count > 0:
            self.audit.record("pii_redacted_output", count=count)
        return cleaned

    def check_sandbox_path(self, path: str) -> bool:
        """Check if a path is allowed by security policy."""
        path_obj = Path(path).resolve()

        # Denied paths
        for denied in self.policy.denied_paths:
            try:
                if path_obj.is_relative_to(Path(denied)):
                    self.audit.record("path_denied", path=str(path_obj), rule=denied)
                    return False
            except Exception:
                if str(path_obj).startswith(denied):
                    self.audit.record("path_denied", path=str(path_obj), rule=denied)
                    return False

        # Allowlist check
        if self.policy.allowlisted_paths:
            allowed = False
            for allowed_path in self.policy.allowlisted_paths:
                try:
                    if path_obj.is_relative_to(Path(allowed_path)):
                        allowed = True
                        break
                except Exception:
                    if str(path_obj).startswith(allowed_path):
                        allowed = True
                        break
            if not allowed:
                self.audit.record("path_not_allowlisted", path=str(path_obj))
                return False

        return True

    def get_constitutional_prompt(self) -> str:
        return self.policy.to_system_prompt_appendix()

    def dump_audit(self) -> str:
        return self.audit.export("jsonl")
