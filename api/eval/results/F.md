# Eval run `F`

- Dataset: bird, 32 questions; model: gemini-3.5-flash-lite
- Options: {'schema': 'retrieved', 'k': 4, 'correction': True, 'fewshot': True, 'evidence': True}
- **Execution accuracy: 17/32 = 53.1%** (95% interval 36.4% to 69.1%)
- Strict (same order): 17/32

| Difficulty | Correct | Total |
|---|---|---|
| simple | 8 | 10 |
| moderate | 7 | 16 |
| challenging | 2 | 6 |

| Outcome | Count |
|---|---|
| correct | 17 |
| wrong | 15 |

Tokens per question: prompt 1002 (max 2016), total 1104. LLM latency p50/p95: 1240/1854 ms (22 live calls).
Self-correction: first try failed on 0 questions, 0 rescued, 0 retries in total.
