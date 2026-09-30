# Eval run `B0R`

- Dataset: bird, 100 questions; model: gemini-3.5-flash-lite
- Options: {'schema': 'retrieved', 'k': 4, 'correction': False, 'fewshot': False, 'evidence': True}
- **Execution accuracy: 52/100 = 52.0%** (95% interval 42.3% to 61.5%)
- Strict (same order): 49/100

| Difficulty | Correct | Total |
|---|---|---|
| simple | 20 | 31 |
| moderate | 25 | 50 |
| challenging | 7 | 19 |

| Outcome | Count |
|---|---|
| correct | 52 |
| declined | 2 |
| wrong | 46 |

Tokens per question: prompt 728 (max 1788), total 830. LLM latency p50/p95: 4206/6735 ms (76 live calls).
