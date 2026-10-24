# Rio Agent Graph: 50-Question Evaluation Suite Report

- **Evaluated At**: 2026-10-24T09:41:39.316979+00:00
- **Mode**: deterministic
- **Model**: `scripted-grounded-50q`
- **Questions Evaluated**: 50 / 50
- **Passed Questions**: 50 (100.0%)
- **Overall Weighted Score**: **81.7%**
- **Critical Regression Gates**: PASSED
- **Evaluation Band**: *Usable with identified gaps (80–89%)*

## Scorecard by Dimension

| Dimension | Weight | Score |
| --- | --- | --- |
| Intent and routing | 15% | 48.8% |
| Context and clarification | 15% | 100.0% |
| Execution and validation | 20% | 100.0% |
| Evidence and accuracy | 25% | 57.8% |
| Safety and auditability | 15% | 100.0% |
| Communication quality | 10% | 99.0% |
| **Weighted Overall Score** | **100%** | **81.7%** |

## Category Performance Breakdown

| Category | Average Score |
| --- | --- |
| Category 1 — Intent understanding and routing | 85.8% |
| Category 2 — Clarification, context and parameter resolution | 82.8% |
| Category 3 — Backtest execution and evidence integrity | 84.2% |
| Category 4 — Performance, strategy attribution and trading decisions | 84.9% |
| Category 5 — Operational health and runtime safety | 85.9% |
| Category 6 — Portfolio risk, position sizing and market regimes | 76.8% |
| Category 7 — Walk-forward testing and strategy laboratory | 77.4% |
| Category 8 — AI agent reasoning, evidence and proposals | 79.7% |
| Category 9 — Configuration versioning, reproducibility and data retention | 79.1% |
| Category 10 — Conversational robustness, multi-step workflows and recovery | 80.1% |

## Detailed Question Results

| # | ID | Title | Category | Weighted Score | Status | Latency |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | **Q01** | Historical profitability | Category 1 — Intent understandin... | 93.8% | PASS | 11ms |
| 2 | **Q02** | Operational diagnosis | Category 1 — Intent understandin... | 93.8% | PASS | 5ms |
| 3 | **Q03** | Configuration intent | Category 1 — Intent understandin... | 75.5% | PASS | 4ms |
| 4 | **Q04** | Historical analysis versus live execution | Category 1 — Intent understandin... | 75.5% | PASS | 5ms |
| 5 | **Q05** | Mixed operational and analytical intent | Category 1 — Intent understandin... | 90.6% | PASS | 4ms |
| 6 | **Q06** | Missing asset | Category 2 — Clarification, cont... | 79.7% | PASS | 4ms |
| 7 | **Q07** | Missing period | Category 2 — Clarification, cont... | 95.8% | PASS | 5ms |
| 8 | **Q08** | Fully specified request | Category 2 — Clarification, cont... | 72.4% | PASS | 4ms |
| 9 | **Q09** | Conflicting context | Category 2 — Clarification, cont... | 75.5% | PASS | 4ms |
| 10 | **Q10** | Explicitly stated assumption | Category 2 — Clarification, cont... | 90.6% | PASS | 4ms |
| 11 | **Q11** | The original regression case | Category 3 — Backtest execution ... | 91.7% | PASS | 5ms |
| 12 | **Q12** | Insufficient historical data | Category 3 — Backtest execution ... | 87.5% | PASS | 3ms |
| 13 | **Q13** | Zero trades | Category 3 — Backtest execution ... | 75.5% | PASS | 4ms |
| 14 | **Q14** | Execution failure | Category 3 — Backtest execution ... | 87.5% | PASS | 4ms |
| 15 | **Q15** | Metric inconsistency | Category 3 — Backtest execution ... | 78.6% | PASS | 4ms |
| 16 | **Q16** | Strategy comparison | Category 4 — Performance, strate... | 78.6% | PASS | 5ms |
| 17 | **Q17** | Winning strategy attribution | Category 4 — Performance, strate... | 78.6% | PASS | 4ms |
| 18 | **Q18** | Rejected candidates | Category 4 — Performance, strate... | 78.6% | PASS | 4ms |
| 19 | **Q19** | Decision-to-order trace | Category 4 — Performance, strate... | 95.0% | PASS | 6ms |
| 20 | **Q20** | Drawdown attribution | Category 4 — Performance, strate... | 93.8% | PASS | 6ms |
| 21 | **Q21** | Bot not ready | Category 5 — Operational health ... | 90.6% | PASS | 4ms |
| 22 | **Q22** | Exchange disconnection | Category 5 — Operational health ... | 93.8% | PASS | 5ms |
| 23 | **Q23** | Risk guard activated | Category 5 — Operational health ... | 70.0% | PASS | 25ms |
| 24 | **Q24** | Balance mismatch | Category 5 — Operational health ... | 87.5% | PASS | 4ms |
| 25 | **Q25** | Scheduler starvation | Category 5 — Operational health ... | 87.5% | PASS | 5ms |
| 26 | **Q26** | Shared quote balance | Category 6 — Portfolio risk, pos... | 75.5% | PASS | 4ms |
| 27 | **Q27** | Dynamic position sizing | Category 6 — Portfolio risk, pos... | 75.5% | PASS | 4ms |
| 28 | **Q28** | High-volatility regime | Category 6 — Portfolio risk, pos... | 78.6% | PASS | 4ms |
| 29 | **Q29** | Conflicting asset signals | Category 6 — Portfolio risk, pos... | 78.6% | PASS | 6ms |
| 30 | **Q30** | Risk limit versus strategy signal | Category 6 — Portfolio risk, pos... | 75.5% | PASS | 5ms |
| 31 | **Q31** | Walk-forward evaluation | Category 7 — Walk-forward testin... | 75.5% | PASS | 5ms |
| 32 | **Q32** | Active day and time windows | Category 7 — Walk-forward testin... | 75.5% | PASS | 6ms |
| 33 | **Q33** | Strategy combination | Category 7 — Walk-forward testin... | 78.6% | PASS | 5ms |
| 34 | **Q34** | Leave-one-strategy-out analysis | Category 7 — Walk-forward testin... | 78.6% | PASS | 5ms |
| 35 | **Q35** | Automatic drift experiment | Category 7 — Walk-forward testin... | 78.6% | PASS | 8ms |
| 36 | **Q36** | Evidence-based proposal | Category 8 — AI agent reasoning,... | 93.8% | PASS | 36ms |
| 37 | **Q37** | Insufficient evidence | Category 8 — AI agent reasoning,... | 75.5% | PASS | 6ms |
| 38 | **Q38** | Conflicting evidence | Category 8 — AI agent reasoning,... | 78.0% | PASS | 8ms |
| 39 | **Q39** | Configuration-change request | Category 8 — AI agent reasoning,... | 75.5% | PASS | 7ms |
| 40 | **Q40** | Unsupported capability | Category 8 — AI agent reasoning,... | 75.5% | PASS | 8ms |
| 41 | **Q41** | Reproduce a historical run | Category 9 — Configuration versi... | 75.5% | PASS | 11ms |
| 42 | **Q42** | Compare configuration versions | Category 9 — Configuration versi... | 75.5% | PASS | 8ms |
| 43 | **Q43** | Experiment isolation | Category 9 — Configuration versi... | 78.6% | PASS | 9ms |
| 44 | **Q44** | Audit a live trading decision | Category 9 — Configuration versi... | 78.6% | PASS | 8ms |
| 45 | **Q45** | Retention and deletion | Category 9 — Configuration versi... | 87.5% | PASS | 11ms |
| 46 | **Q46** | Follow-up context | Category 10 — Conversational rob... | 73.4% | PASS | 7ms |
| 47 | **Q47** | Ambiguous follow-up | Category 10 — Conversational rob... | 81.8% | PASS | 14ms |
| 48 | **Q48** | Partial tool failure | Category 10 — Conversational rob... | 75.5% | PASS | 20ms |
| 49 | **Q49** | Recovery after a clarification | Category 10 — Conversational rob... | 79.7% | PASS | 8ms |
| 50 | **Q50** | End-to-end evidence-based investigation | Category 10 — Conversational rob... | 90.0% | PASS | 8ms |