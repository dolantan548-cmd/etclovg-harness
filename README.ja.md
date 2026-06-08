<!-- README.ja.md — ETCLOVG Harness 日本語ドキュメント -->

<h1 align="center">ETCLOVG Harness</h1>
<h3 align="center">プロダクショングレード七層エージェントフレームワーク</h3>
<h4 align="center"><code>E · T · C · L · O · V · G</code></h4>

---

## ETCLOVG とは

**ETCLOVG** は、プロダクショングレードの AI エージェントシステムを評価・構築するための七次元分類法です。

| 層 | 名称 | 中核的関心事 |
|:---:|:---|:---|
| **E** | 実行環境 (Execution) | コードはどこで実行されるか？7種類のサンドボックス |
| **T** | ツール (Tools) | ツールはどう接続するか？MCP、A2A、Function Calling 等 |
| **C** | コンテキスト (Context) | エージェントはどう記憶するか？3層記憶＋段階的圧縮 |
| **L** | ライフサイクル (Lifecycle) | どう計画し行動するか？PERループ、ReAct、マルチエージェント |
| **O** | 可観測性 (Observability) | 何が起きたか把握できるか？トレーシング、コスト、ハートビート |
| **V** | 検証 (Verification) | 出力は正しいか？事前スクリーニング、事後検証 |
| **G** | ガバナンス (Governance) | 安全か？4層防御、PII検出、憲法的AI制約 |

## 170以上のフレームワークを分析

ETCLOVG Harness は、GenericAgent、Hermes Agent、OpenClaw、Claude Code、CodeWhale を含む **170以上のオープンソースエージェントフレームワーク** の系統的分析から導出されました。

## クイックスタート

```bash
git clone https://github.com/dolantan548-cmd/etclovg-harness.git
cd etclovg-harness
pip install -r requirements.txt
set OPENAI_API_KEY=sk-...
python test_agent.py
python agent.py "フランスの首都は？"
```

## 使用例

```python
from etclovg import ETCLOVGHarness

harness = ETCLOVGHarness(api_key="sk-...", model="gpt-4o")
result = harness.run("最近のAI技術の進歩について教えてください")
print(result["output"])
print(f"コスト: ${result['cost_estimate_usd']:.4f}")
```

## アーキテクチャ

```
ETCLOVG Harness
├── E 層: サンドボックス実行環境
├── T 層: マルチプロトコルツール登録
├── C 層: 三層コンテキスト管理
├── L 層: Plan→Execute→Reflect ループ
├── O 層: トレーシング・コスト・ハートビート
├── V 層: 事前検証・事後検証・回帰テスト
└── G 層: ガバナンス・PIIスクラビング・監査
```

## 比較

| フレームワーク | E | T | C | L | O | V | G | 総合 |
|:---|---|---|---|---|---|---|---|---|
| ETCLOVG Harness | A | A | A | A | A | A- | A | **A** |
| GenericAgent | A- | A+ | A- | A | B+ | B | A+ | 84% |
| Hermes Agent | A | A | A | A | A | B+ | A- | 88% |

## ライセンス

MIT License

---

*「Harness-as-Assumption — アーキテクチャの前提を明示化し、生産品質をデフォルトに。」*
