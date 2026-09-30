# Eval run `B0_unquoted` (schema text did not quote names like "First Date"; superseded by B0)

- Dataset: bird, 100 questions; model: gemini-3.5-flash-lite
- Options: {'schema': 'full', 'correction': False, 'fewshot': False, 'evidence': True}
- **Execution accuracy: 52/100 = 52.0%** (95% interval 42.3% to 61.5%)
- Strict (same order): 50/100

| Difficulty | Correct | Total |
|---|---|---|
| simple | 20 | 31 |
| moderate | 26 | 50 |
| challenging | 6 | 19 |

| Outcome | Count |
|---|---|
| blocked | 1 |
| correct | 52 |
| db_error | 1 |
| wrong | 46 |

Tokens per question: prompt 769 (max 1813), total 872. LLM latency p50/p95: 4302/7561 ms (80 live calls).
