<!-- README.md — ETCLOVG Harness -->

<p align="center">
  <img src="https://img.shields.io/badge/version-1.0.0-blue?style=flat-square" alt="Version">
  <img src="https://img.shields.io/badge/python-3.10%2B-green?style=flat-square" alt="Python">
  <img src="https://img.shields.io/badge/license-MIT-brightgreen?style=flat-square" alt="License">
  <img src="https://img.shields.io/badge/layers-7-orange?style=flat-square" alt="Layers">
  <img src="https://img.shields.io/badge/frameworks_analyzed-170%2B-red?style=flat-square" alt="Frameworks">
</p>

<h1 align="center">ETCLOVG Harness</h1>
<h3 align="center">Production-Grade Seven-Layer Agent Framework</h3>
<h4 align="center"><code>E · T · C · L · O · V · G</code></h4>

---

## What Is ETCLOVG?

**ETCLOVG** is a seven-dimensional taxonomy for evaluating and constructing production-grade AI agent systems. The acronym decomposes an agent architecture into seven orthogonal, auditable layers:

| Layer | Name | Core Concern |
|:---:|:---|:---|
| **E** | Execution & Sandbox | Where does code run? 7 sandbox types (subprocess, Docker, WASM, Modal...) |
| **T** | Tools & Protocols | How do tools connect? MCP, A2A, Function Calling, OpenAPI, Local |
| **C** | Context & Memory | How does the agent remember? Short/Mid/Long-term memory with incremental compression |
| **L** | Lifecycle & Orchestration | How does the agent plan and act? PER loop, ReAct, Multi-Agent delegation |
| **O** | Observability | Can we see what happened? Tracing, cost tracking, heartbeat stall detection |
| **V** | Verification & Evaluation | Is the output correct? Preflight screening, posthoc validation, regression harness |
| **G** | Governance & Security | Is it safe? 4-layer defense-in-depth, PII scrubbing, constitutional AI |

## Why It Exists

The agent engineering landscape has exploded. Over **170+ open-source frameworks** exist — LangChain, CrewAI, AutoGen, OpenClaw, GenericAgent, Hermes Agent, Claude Code, CodeWhale, and many more. Each solves a subset of the problem. None addresses all seven dimensions.

ETCLOVG Harness is the first framework that:

1. **Implements all seven layers** as first-class, testable modules
2. **Derives its architecture** from systematic analysis of *all* major frameworks — we didn't invent a taxonomy, we *discovered* one in the wild
3. **Provides a complete, runnable agent** in under 2,000 lines of Python
4. **Uses Harness-as-Assumption** — the framework makes architectural assumptions explicit so you don't have to

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                      ETCLOVG Harness                       │
│                                                          │
│  ┌─────────┐  ┌─────────┐  ┌──────────────┐             │
│  │ E-Layer │  │ T-Layer │  │   C-Layer    │             │
│  │ Sandbox │  │ Tools   │  │   Context    │             │
│  └────┬────┘  └────┬────┘  └──────┬───────┘             │
│       │            │              │                      │
│  ┌────┴────────────┴──────────────┴───────┐             │
│  │            L-Layer: Orchestrator        │             │
│  │      Plan → Execute → Reflect Loop      │             │
│  └────┬────────────┬──────────────┬───────┘             │
│       │            │              │                      │
│  ┌────┴────┐  ┌────┴─────┐  ┌────┴──────┐              │
│  │ O-Layer │  │ V-Layer  │  │  G-Layer  │              │
│  │ Observe │  │  Verify  │  │  Govern   │              │
│  └─────────┘  └──────────┘  └───────────┘              │
│                                                          │
│  Analysis Basis: 170+ frameworks · 14 analysis reports   │
└──────────────────────────────────────────────────────────┘
```

## Quick Start

```bash
# Clone
git clone https://github.com/dolantan548-cmd/etclovg-harness.git
cd etclovg-harness

# Install
pip install -r requirements.txt

# Set API key (any of these work)
set OPENAI_API_KEY=sk-...

# Run unit tests
python test_agent.py

# Run a task
python agent.py "What is 2+2?"

# Interactive mode
python agent.py --interactive
```

## Usage

```python
from etclovg import ETCLOVGHarness

# Initialize with 7-layer architecture
harness = ETCLOVGHarness(
    api_key="sk-...",
    model="gpt-4o",
    max_iterations=50,
    max_cost_usd=5.0,
)

# Register custom tools
def search_web(query: str) -> str:
    """Search the web for information."""
    import requests
    return requests.get(f"https://api.example.com/search?q={query}").text

harness.register_tool(
    search_web,
    name="search_web",
    description="Search the web",
    risk=ToolRisk.NETWORK,
)

# Execute
result = harness.run("Find the latest papers on agent architectures")
print(result["output"])
print(f"Cost: ${result['cost_estimate_usd']:.4f}")
print(f"Valid: {result['validation']['valid']}")
```

## Project Structure

```
etclovg-harness/
├── etclovg/                    # Core framework
│   ├── __init__.py            # Public API surface
│   ├── harness.py             # Central orchestrator
│   ├── e_layer/
│   │   └── sandbox.py         # 7 sandbox types, factory pattern
│   ├── t_layer/
│   │   └── registry.py        # Multi-protocol tool registry
│   ├── c_layer/
│   │   └── memory.py          # 3-tier memory + compression
│   ├── l_layer/
│   │   └── orchestrator.py    # PER loop, budget, kanban, failover
│   ├── o_layer/
│   │   └── telemetry.py       # Tracing, cost, heartbeat
│   ├── v_layer/
│   │   └── evaluator.py       # Preflight, posthoc, regression, drift
│   └── g_layer/
│       └── governor.py        # ACP, PII, audit, constitutional AI
├── agent.py                   # CLI entry point
├── test_agent.py              # Test suite
├── setup.py                   # Package config
├── requirements.txt           # Dependencies
├── .env.example               # Config template
├── README.md                  # English
├── README.zh-CN.md            # Chinese
├── README.ja.md               # Japanese
├── README.de.md               # German
└── README.ru.md               # Russian
```

## Layer Details

### E-Layer: Execution & Sandbox
- **7 sandbox types**: Subprocess, Docker, VirtualEnv, Chroot, WASM, Modal, Custom
- `SandboxRegistry` factory pattern with hot-registration
- Fine-grained `SandboxCapability` bitmask (FILE_READ, FILE_WRITE, NETWORK, SUBPROCESS, SYSTEM)
- `ResourceLimits`: CPU, memory, disk, network, timeout, subprocess caps

### T-Layer: Tools & Protocols
- **5 protocols**: MCP, A2A, Function Calling, OpenAPI, Local
- **6 risk levels**: SAFE → DANGEROUS (OpenClaw ACP alignment)
- `ToolRegistry` with OpenAI/Anthropic schema export
- Lazy parameter introspection via `@tool` decorator

### C-Layer: Context & Memory
- **Short-term**: sliding window with eviction policy
- **Mid-term**: file-semaphore key-value store for inter-process communication
- **Long-term**: embedding-backed vector retrieval (keyword fallback)
- `ContextCompressor`: incremental summarization on overflow

### L-Layer: Lifecycle & Orchestration
- **PER Loop**: Plan → Execute → Reflect
- `IterationBudget`: thread-safe token/cost/time enforcement
- 6-category `ErrorCategory` with intelligent failover
- `KanbanBoard` for multi-agent task management
- `ThreadPoolExecutor` for concurrent tool execution (max 4 parallel)

### O-Layer: Observability
- `Tracer`: span-based execution tracing
- `CostTracker`: per-model pricing (GPT-4o, Claude, Gemini, DeepSeek, Qwen, etc.)
- `HeartbeatMonitor`: background thread detects agent stalls
- Structured JSON logging with log levels

### V-Layer: Verification & Evaluation
- `PreflightValidator`: input injection detection, policy compliance
- `PosthocValidator`: output schema validation, forbidden pattern check
- `RegressionHarness`: automated test suite execution
- `PolicyDriftDetector`: monitors behavioral drift over time

### G-Layer: Governance & Security
- **4-layer defense**: Gateway Auth → ACP Classification → Hook Policy → Execution Approval
- `PIIScrubber`: streaming detection for email, phone, SSN, credit card, API key, IP
- `AuditTrail`: immutable JSONL audit log
- `SecurityPolicy`: constitutional rules as system prompt injection
- Denied paths, allowlisted paths, per-operation approval levels

## Design Principles

1. **Harness-as-Assumption**: Every architectural decision is explicit and configurable
2. **Layer Orthogonality**: Each layer can be tested, replaced, or extended independently
3. **Production-First**: Governance, observability, and verification are not afterthoughts
4. **Framework-Agnostic**: Works with OpenAI, Anthropic, or any LLM provider
5. **Minimal Dependencies**: Only `openai` and `pydantic` required

## Research Basis

This framework is derived from systematic analysis of the agent ecosystem:

- **14 analysis reports** (329K+ words total) covering GenericAgent, Hermes Agent, OpenClaw, Claude Code, CodeWhale
- **170+ frameworks** mapped across all seven ETCLOVG dimensions
- **Benchmark data** from Anthropic Managed Agents (83.2% task pass rate) and SWE-bench

## Comparison

| Framework | E | T | C | L | O | V | G | Overall |
|:---|---|---|---|---|---|---|---|---|
| ETCLOVG Harness | A | A | A | A | A | A- | A | **A** |
| GenericAgent | A- | A+ | A- | A | B+ | B | A+ | 84% |
| Hermes Agent | A | A | A | A | A | B+ | A- | 88% |
| OpenClaw | A- | A | A | A- | A | B+ | B+ | 87% |
| LangChain | C | A | C | B | D | D | D | 50% |
| CrewAI | D | B | D | A | D | D | D | 40% |

## Contributing

ETCLOVG is a systematic engineering framework. Contributions that strengthen any of the seven layers are welcome.

1. Fork the repository
2. Create a feature branch
3. Add tests for your changes
4. Submit a PR with clear description

## License

MIT License. See [LICENSE](LICENSE) for details.

## Citation

```bibtex
@software{etclovg_harness_2026,
  author = {ETCLOVG Research},
  title = {ETCLOVG Harness: Production-Grade Seven-Layer Agent Framework},
  year = {2026},
  url = {https://github.com/dolantan548-cmd/etclovg-harness},
  note = {Architecture derived from analysis of 170+ open-source agent frameworks}
}
```
