<!-- README.zh-CN.md — ETCLOVG Harness 中文文档 -->

<h1 align="center">ETCLOVG Harness</h1>
<h3 align="center">生产级七层智能体框架</h3>
<h4 align="center"><code>E · T · C · L · O · V · G</code></h4>

---

## 什么是 ETCLOVG？

**ETCLOVG** 是一个用于评估和构建生产级 AI 智能体系统的七维分类法。该缩写将智能体架构分解为七个正交、可审计的层次：

| 层 | 名称 | 核心关注点 |
|:---:|:---|:---|
| **E** | 执行与沙箱 (Execution) | 代码在哪里运行？7 种沙箱类型（Subprocess、Docker、WASM、Modal…） |
| **T** | 工具与协议 (Tools) | 工具如何连接？MCP、A2A、Function Calling、OpenAPI、Local |
| **C** | 上下文与记忆 (Context) | 智能体如何记忆？短/中/长期记忆，增量压缩 |
| **L** | 生命周期与编排 (Lifecycle) | 智能体如何规划与行动？PER 循环、ReAct、多智能体协作 |
| **O** | 可观测性 (Observability) | 我们能看到发生了什么吗？追踪、成本核算、心跳卡死检测 |
| **V** | 验证与评估 (Verification) | 输出是否正确？预检筛查、事后验证、回归测试 |
| **G** | 治理与安全 (Governance) | 是否安全？四层纵深防御、PII 脱敏、宪法式 AI |

## 为什么需要它

智能体工程领域已经爆发式增长。存在 **170+ 开源框架** — LangChain、CrewAI、AutoGen、OpenClaw、GenericAgent、Hermes Agent、Claude Code、CodeWhale 等。每个框架都解决了一部分问题，但没有任何框架覆盖全部七个维度。

ETCLOVG Harness 是首个：

1. **实现全部七层** 作为一等公民、可测试的模块
2. **从系统分析中推导架构** — 我们不是发明分类法，而是在真实世界中 **发现** 了它
3. **提供完整可运行的智能体**，不到 2000 行 Python 代码
4. **使用 Harness-as-Assumption** — 框架将架构假设显式化，无需你做决定

## 快速开始

```bash
git clone https://github.com/dolantan548-cmd/etclovg-harness.git
cd etclovg-harness
pip install -r requirements.txt

# 设置 API 密钥
set OPENAI_API_KEY=sk-...

# 运行单元测试
python test_agent.py

# 执行任务
python agent.py "法国的首都是什么？"

# 交互模式
python agent.py --interactive
```

## 使用示例

```python
from etclovg import ETCLOVGHarness

harness = ETCLOVGHarness(api_key="sk-...", model="gpt-4o")
result = harness.run("总结今天AI领域的重大新闻")
print(result["output"])
print(f"成本: ${result['cost_estimate_usd']:.4f}")
```

## 项目结构

```
etclovg-harness/
├── etclovg/                  # 核心框架
│   ├── e_layer/sandbox.py    # 7种沙箱类型
│   ├── t_layer/registry.py   # 多协议工具注册
│   ├── c_layer/memory.py     # 三级记忆 + 压缩
│   ├── l_layer/orchestrator.py # PER循环、预算
│   ├── o_layer/telemetry.py  # 追踪、成本、心跳
│   ├── v_layer/evaluator.py  # 预检、验证、回归
│   ├── g_layer/governor.py   # ACP、PII、审计
│   └── harness.py            # 中央调度器
├── agent.py                  # CLI入口
├── test_agent.py             # 测试套件
└── README.md                 # 英文主文档
```

## 对比

| 框架 | E | T | C | L | O | V | G | 总分 |
|:---|---|---|---|---|---|---|---|---|
| ETCLOVG Harness | A | A | A | A | A | A- | A | **A** |
| GenericAgent | A- | A+ | A- | A | B+ | B | A+ | 84% |
| Hermes Agent | A | A | A | A | A | B+ | A- | 88% |
| OpenClaw | A- | A | A | A- | A | B+ | B+ | 87% |

## 许可证

MIT License

---

*"Harness-as-Assumption — 让架构假设显式化，让生产级质量成为默认。"*
