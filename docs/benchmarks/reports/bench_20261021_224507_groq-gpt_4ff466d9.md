# Rio Agent Grounding & Quality Gate Benchmark Report

- **Quality Gate Verdict**: **FAILED**
- **Model / Adapter**: `groq-gpt`
- **Execution Mode**: `live` (trials: `1`)
- **Evaluated At**: `2026-10-21T22:45:07.964150+00:00`
- **Git Revision**: `4ff466d90` on `main` (dirty)
- **Suite Version**: `2.0-grounded` | Python `3.12.7`
- **Overall Pass Rate**: **19/20 (95.0%)**
- **Mean Composite Score**: **99.3%**
  - Tool Selection & Routing: `100.0%`
  - Factual Accuracy (Tool Grounded): `100.0%`
  - Unsupported Claims Rate: `0.0%`
  - Epistemic Honesty: `98.3%`
  - Consistency (Cross-Prompt & Trials): `98.3%`
- **Latency**: `p50 = 20519.5 ms` | `p95 = 37308.2 ms`

### Quality Gate Failure Reasons:
- ❌ Failed questions (1): Q15

## Summary by Question

| ID | Question | Category | Tool Selection | Fact Accuracy | Epistemic | Unsupported | Consistency | Total | Status | Latency |
| :- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Q01** | Is Rio healthy and currently trading? | Live operations and account state | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 3062.6ms |
| **Q02** | What are my current balances, available cash, and open orders? | Live operations and account state | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 6884.5ms |
| **Q03** | Why hasn't BTC_USD placed an order recently? | Live operations and account state | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 23208.4ms |
| **Q04** | Are orders failing, being rejected, or taking longer to execute? | Live operations and account state | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 15281.8ms |
| **Q05** | Why did Rio buy or sell this asset? | Decisions and configuration | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 24868.4ms |
| **Q06** | Why was a particular strategy's signal rejected? | Decisions and configuration | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 14599.4ms |
| **Q07** | What changed between the current configuration and the configuration used for this order? | Decisions and configuration | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 25430.2ms |
| **Q08** | What configuration change do you recommend, and why? | Decisions and configuration | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 25489.0ms |
| **Q09** | How has the bot performed over the last 24 hours, 7 days, or 30 days? | Performance and attribution | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 28540.2ms |
| **Q10** | Which strategies contributed most to profit or loss? | Performance and attribution | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 24887.6ms |
| **Q11** | Has strategy performance changed by market regime? | Performance and attribution | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 23333.1ms |
| **Q12** | Is the bot's live execution diverging from its backtest? | Performance and attribution | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 23287.2ms |
| **Q13** | Would this strategy have been profitable on historical data? | Backtesting and experiments | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 9637.6ms |
| **Q14** | Which candidate configuration performs best in walk-forward validation? | Backtesting and experiments | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 25687.7ms |
| **Q15** | Why did this experiment run, and what triggered it? | Backtesting and experiments | 100% | 100% | 67% | 0% | 67% | **86.7%** | **FAIL** | 17830.5ms |
| **Q16** | Has the bot become inactive or drifted enough to justify a new experiment? | Backtesting and experiments | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 13636.2ms |
| **Q17** | What is my current portfolio exposure, drawdown, and concentration risk? | Risk, system behavior, and data governance | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 37308.2ms |
| **Q18** | Why did the risk manager or guard prevent a trade? | Risk, system behavior, and data governance | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 14243.2ms |
| **Q19** | What happened during this run, from schedule tick through order execution? | Risk, system behavior, and data governance | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 13576.6ms |
| **Q20** | What data will expire, what will be retained, and why was a record deleted or skipped? | Risk, system behavior, and data governance | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 16001.1ms |

## Category Breakdown

| Category | Passed | Mean Tool Sel | Mean Fact Acc | Mean Epistemic | Mean Unsupported | Mean Total |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Live operations and account state** | 4/4 | 100.0% | 100.0% | 100.0% | 0.0% | **100.0%** |
| **Decisions and configuration** | 4/4 | 100.0% | 100.0% | 100.0% | 0.0% | **100.0%** |
| **Performance and attribution** | 4/4 | 100.0% | 100.0% | 100.0% | 0.0% | **100.0%** |
| **Backtesting and experiments** | 3/4 | 100.0% | 100.0% | 91.7% | 0.0% | **96.7%** |
| **Risk, system behavior, and data governance** | 4/4 | 100.0% | 100.0% | 100.0% | 0.0% | **100.0%** |