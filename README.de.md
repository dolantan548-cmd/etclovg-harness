<!-- README.de.md — ETCLOVG Harness Deutsche Dokumentation -->

<h1 align="center">ETCLOVG Harness</h1>
<h3 align="center">Produktionsreifes Sieben-Schichten-Agenten-Framework</h3>
<h4 align="center"><code>E · T · C · L · O · V · G</code></h4>

---

## Was ist ETCLOVG?

**ETCLOVG** ist eine siebendimensionale Taxonomie zur Bewertung und Konstruktion produktionsreifer KI-Agentensysteme.

| Schicht | Name | Kernfrage |
|:---:|:---|:---|
| **E** | Ausführung & Sandbox | Wo läuft der Code? 7 Sandbox-Typen (Subprocess, Docker, WASM…) |
| **T** | Werkzeuge & Protokolle | Wie verbinden sich Werkzeuge? MCP, A2A, Function Calling, OpenAPI |
| **C** | Kontext & Gedächtnis | Wie erinnert sich der Agent? Dreistufiges Gedächtnis mit Kompression |
| **L** | Lebenszyklus | Wie plant und handelt der Agent? PER-Schleife, Multi-Agent-Delegation |
| **O** | Beobachtbarkeit | Können wir sehen, was passiert? Tracing, Kostenverfolgung, Heartbeat-Erkennung |
| **V** | Verifikation | Ist die Ausgabe korrekt? Vorabprüfung, Nachvalidierung, Regressionstests |
| **G** | Governance & Sicherheit | Ist es sicher? 4-Schichten-Verteidigung, PII-Bereinigung, konstitutionelle KI |

## Basierend auf 170+ Frameworks

ETCLOVG Harness wurde durch systematische Analyse von über **170 Open-Source-Agenten-Frameworks** abgeleitet, darunter GenericAgent, Hermes Agent, OpenClaw, Claude Code und CodeWhale.

## Schnellstart

```bash
git clone https://github.com/dolantan548-cmd/etclovg-harness.git
cd etclovg-harness
pip install -r requirements.txt
set OPENAI_API_KEY=sk-...
python test_agent.py
python agent.py "Was ist die Hauptstadt von Frankreich?"
```

## Verwendung

```python
from etclovg import ETCLOVGHarness

harness = ETCLOVGHarness(api_key="sk-...", model="gpt-4o")
result = harness.run("Erzähl mir von den neuesten Fortschritten in der KI")
print(result["output"])
print(f"Kosten: ${result['cost_estimate_usd']:.4f}")
```

## Architektur

```
ETCLOVG Harness
├── E-Schicht: Sandbox-Ausführungsumgebung
├── T-Schicht: Multiprotokoll-Werkzeugregistrierung
├── C-Schicht: Dreistufige Kontextverwaltung
├── L-Schicht: Plan→Ausführen→Reflektieren-Schleife
├── O-Schicht: Tracing, Kosten, Heartbeat
├── V-Schicht: Validierung, Verifikation, Regression
└── G-Schicht: Governance, PII-Scrubbing, Audit
```

## Vergleich

| Framework | E | T | C | L | O | V | G | Gesamt |
|:---|---|---|---|---|---|---|---|---|
| ETCLOVG Harness | A | A | A | A | A | A- | A | **A** |
| GenericAgent | A- | A+ | A- | A | B+ | B | A+ | 84% |
| Hermes Agent | A | A | A | A | A | B+ | A- | 88% |

## Lizenz

MIT License

---

*„Harness-as-Assumption — Architekturannahmen explizit machen, Produktionsqualität zum Standard machen."*
