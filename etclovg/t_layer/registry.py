"""
T-Layer: Tool Interface & Protocol

Implements a multi-protocol tool registry supporting:
  - MCP (Model Context Protocol) — server/client lifecycle
  - A2A (Agent-to-Agent) — inter-agent tool delegation
  - Function Calling — OpenAI/Anthropic native tool schemas
  - OpenAPI — REST API auto-wrapping as tools
  - Local Functions — in-process Python callables

Design Philosophy:
  <GenericAgent: LLM-driven everything — tools are discovered, selected,
   and composed by the model at runtime. The framework provides trigger
   mechanisms and protocol adapters, not hard-coded tool pipelines.>
"""

from __future__ import annotations

import json
import enum
import inspect
import hashlib
import dataclasses
from typing import Any, Callable, Dict, List, Optional, Union, get_type_hints
from pathlib import Path


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

class ToolProtocol(enum.Enum):
    FUNCTION_CALLING = "function_calling"
    MCP             = "mcp"
    A2A             = "a2a"
    OPENAPI         = "openapi"
    LOCAL           = "local"


class ToolRisk(enum.IntEnum):
    """Six-level risk classification (aligned with OpenClaw ACP)."""
    SAFE        = 0  # Read-only, no side effects
    READ_WRITE  = 1  # Reads + creates new files
    MODIFY      = 2  # Modifies existing resources
    DELETE      = 3  # Deletes resources
    SYSTEM      = 4  # System-level operations
    DANGEROUS   = 5  # Arbitrary code execution, shell


@dataclasses.dataclass
class ToolParameter:
    name:         str
    type_:        str
    description:  str
    required:     bool = True
    default:      Any = None
    enum_values:  Optional[List[str]] = None

    def to_openai_schema(self) -> dict:
        schema: dict = {
            "type": "string" if self.type_ == "str" else self.type_,
            "description": self.description,
        }
        if self.enum_values:
            schema["enum"] = self.enum_values
        return schema


@dataclasses.dataclass
class ToolDefinition:
    """Complete tool metadata — serializable to OpenAI/Anthropic function schema."""
    name:         str
    description:  str
    parameters:   List[ToolParameter]
    protocol:     ToolProtocol = ToolProtocol.LOCAL
    risk:         ToolRisk     = ToolRisk.SAFE
    handler:      Optional[Callable] = dataclasses.field(default=None, repr=False)
    source:       str          = ""  # MCP server name, OpenAPI URL, module path
    version:      str          = "1.0.0"
    tags:         List[str]    = dataclasses.field(default_factory=list)

    def to_openai_function(self) -> dict:
        """Emit OpenAI-compatible function-calling schema."""
        properties = {}
        required = []
        for p in self.parameters:
            properties[p.name] = p.to_openai_schema()
            if p.required:
                required.append(p.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    @property
    def signature_hash(self) -> str:
        raw = f"{self.name}:{json.dumps([dataclasses.asdict(p) for p in self.parameters], sort_keys=True)}"
        return hashlib.sha256(raw.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Tool Registry
# ---------------------------------------------------------------------------

class ToolRegistry:
    """
    Central tool catalog supporting multi-protocol registration.

    Features:
      - Lazy MCP server connection (connect on first invoke)
      - LLM-driven tool discovery — the model decides which tools to use
      - Risk-aware filtering (governor can drop tools above certain risk)
      - Schema export to OpenAI/Anthropic format
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}
        self._mcp_clients: Dict[str, Any] = {}  # Lazy MCP connections
        self._openapi_clients: Dict[str, Any] = {}

    # -- Registration --------------------------------------------------------

    def register(
        self,
        name: str,
        handler: Callable,
        *,
        description: str = "",
        protocol: ToolProtocol = ToolProtocol.LOCAL,
        risk: ToolRisk = ToolRisk.SAFE,
        tags: Optional[List[str]] = None,
        source: str = "",
    ) -> ToolDefinition:
        """Register a local Python function as a tool."""
        params = self._introspect_parameters(handler)
        tool = ToolDefinition(
            name=name,
            description=description or (handler.__doc__ or "").split("\n")[0].strip(),
            parameters=params,
            protocol=protocol,
            risk=risk,
            handler=handler,
            source=source or handler.__module__,
            tags=tags or [],
        )
        self._tools[name] = tool
        return tool

    def register_tool_definition(self, tool: ToolDefinition) -> None:
        """Register a pre-built ToolDefinition (e.g., from MCP list_tools)."""
        self._tools[tool.name] = tool

    def unregister(self, name: str) -> None:
        self._tools.pop(name, None)

    # -- Discovery -----------------------------------------------------------

    def list_tools(
        self,
        max_risk: ToolRisk = ToolRisk.MODIFY,
        tags: Optional[List[str]] = None,
    ) -> List[ToolDefinition]:
        """Return tools filtered by risk ceiling and optional tag matching."""
        result = []
        for tool in self._tools.values():
            if tool.risk > max_risk:
                continue
            if tags and not any(t in tool.tags for t in tags):
                continue
            result.append(tool)
        return result

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def get_handler(self, name: str) -> Optional[Callable]:
        tool = self._tools.get(name)
        return tool.handler if tool else None

    # -- Execution -----------------------------------------------------------

    def invoke(self, name: str, arguments: Dict[str, Any]) -> Any:
        """Invoke a tool by name with keyword arguments."""
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Tool not found: {name}")

        if tool.handler is None:
            raise RuntimeError(f"Tool '{name}' has no bound handler (MCP/OpenAPI tools need lazy connect)")

        return tool.handler(**arguments)

    def invoke_safe(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Invoke with error catching — suitable for LLM loop consumption."""
        try:
            result = self.invoke(name, arguments)
            return {"success": True, "result": result}
        except Exception as exc:
            return {"success": False, "error": str(exc), "error_type": type(exc).__name__}

    # -- Schema Export -------------------------------------------------------

    def to_openai_tools(self, max_risk: ToolRisk = ToolRisk.MODIFY) -> List[dict]:
        """Export as OpenAI tools array for chat completion API."""
        return [t.to_openai_function() for t in self.list_tools(max_risk=max_risk)]

    def to_system_prompt(self, max_risk: ToolRisk = ToolRisk.MODIFY) -> str:
        """Generate a compact tool listing for system prompt injection."""
        lines = ["Available tools:"]
        for t in self.list_tools(max_risk=max_risk):
            params_str = ", ".join(
                f"{p.name}: {p.type_}" + ("" if p.required else "?")
                for p in t.parameters
            )
            lines.append(f"  {t.name}({params_str}) — {t.description[:120]}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._tools)

    # -- Helpers -------------------------------------------------------------

    @staticmethod
    def _introspect_parameters(func: Callable) -> List[ToolParameter]:
        hints = get_type_hints(func) if hasattr(func, "__annotations__") else {}
        sig = inspect.signature(func)
        params = []
        for name, param in sig.parameters.items():
            if name in ("self", "cls"):
                continue
            type_hint = hints.get(name, str)
            type_str = getattr(type_hint, "__name__", str(type_hint))
            required = param.default is inspect.Parameter.empty
            default = None if required else param.default
            params.append(ToolParameter(
                name=name,
                type_=type_str,
                description=f"Parameter '{name}'",
                required=required,
                default=default,
            ))
        return params


# ---------------------------------------------------------------------------
# Tool decorator (convenience)
# ---------------------------------------------------------------------------

_registry_instance: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    global _registry_instance
    if _registry_instance is None:
        _registry_instance = ToolRegistry()
    return _registry_instance


def tool(
    name: Optional[str] = None,
    *,
    description: str = "",
    risk: ToolRisk = ToolRisk.SAFE,
    tags: Optional[List[str]] = None,
):
    """Decorator: register a function as a callable tool."""
    def decorator(func: Callable) -> Callable:
        tool_name = name or func.__name__
        get_registry().register(
            name=tool_name,
            handler=func,
            description=description,
            risk=risk,
            tags=tags,
        )
        return func
    return decorator
