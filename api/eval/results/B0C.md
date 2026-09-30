# Eval run `B0C`

- Dataset: bird, 100 questions; model: gemini-3.5-flash-lite
- Options: {'schema': 'full', 'k': None, 'correction': True, 'fewshot': False, 'evidence': True}
- **Execution accuracy: 52/100 = 52.0%** (95% interval 42.3% to 61.5%)
- Strict (same order): 49/100

| Difficulty | Correct | Total |
|---|---|---|
| simple | 19 | 31 |
| moderate | 26 | 50 |
| challenging | 7 | 19 |

| Outcome | Count |
|---|---|
| correct | 52 |
| declined | 1 |
| wrong | 47 |

Tokens per question: prompt 832 (max 1854), total 939. LLM latency p50/p95: 9175/15835 ms (2 live calls).
Self-correction: first try failed on 2 questions, 0 rescued, 2 retries in total.
