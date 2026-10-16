# Rio 20-Question Acceptance & Grounding Benchmark Report

- **Model / Adapter**: `scripted-grounded-v1`
- **Execution Mode**: `deterministic`
- **Evaluated At**: `2026-10-16T19:26:50.308980+00:00`
- **Overall Pass Rate**: **20/20 (100.0%)**
- **Mean Composite Score**: **100.0%**
  - Route & Tool Selection (20%): `100.0%`
  - Grounded Fact Recall (40%): `100.0%`
  - Epistemic Guardrails (25%): `100.0%`
  - Cross-Prompt Consistency (15%): `100.0%`
- **Latency**: `p50 = 4.6 ms` | `p95 = 13.4 ms`

## Summary by Question (Q01–Q20)

| ID | Question | Category | Baseline | Route/Tool | Fact Recall | Epistemic | Consistency | Total | Status | Latency |
| :- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Q01** | Is Rio healthy and currently trading? | Live operations and account state | Good foundation | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 4.1ms |
| **Q02** | What are my current balances, available cash, and open orders? | Live operations and account state | Good foundation | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 4.2ms |
| **Q03** | Why hasn't BTC_USD placed an order recently? | Live operations and account state | Partial | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 4.2ms |
| **Q04** | Are orders failing, being rejected, or taking longer to execute? | Live operations and account state | Good foundation | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 3.1ms |
| **Q05** | Why did Rio buy or sell this asset? | Decisions and configuration | Good foundation | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 10.3ms |
| **Q06** | Why was a particular strategy's signal rejected? | Decisions and configuration | Partial | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 10.6ms |
| **Q07** | What changed between the current configuration and the configuration used for this order? | Decisions and configuration | Good foundation | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 11.7ms |
| **Q08** | What configuration change do you recommend, and why? | Decisions and configuration | Implemented with guardrails | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 15.9ms |
| **Q09** | How has the bot performed over the last 24 hours, 7 days, or 30 days? | Performance and attribution | Good foundation | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 6.2ms |
| **Q10** | Which strategies contributed most to profit or loss? | Performance and attribution | Partial — validate accounting | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 5.0ms |
| **Q11** | Has strategy performance changed by market regime? | Performance and attribution | Partial | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 5.1ms |
| **Q12** | Is the bot's live execution diverging from its backtest? | Performance and attribution | Partial | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 4.8ms |
| **Q13** | Would this strategy have been profitable on historical data? | Backtesting and experiments | Implemented | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 3.4ms |
| **Q14** | Which candidate configuration performs best in walk-forward validation? | Backtesting and experiments | Partial | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 4.5ms |
| **Q15** | Why did this experiment run, and what triggered it? | Backtesting and experiments | Partial | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 11.0ms |
| **Q16** | Has the bot become inactive or drifted enough to justify a new experiment? | Backtesting and experiments | Partial | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 3.5ms |
| **Q17** | What is my current portfolio exposure, drawdown, and concentration risk? | Risk, system behavior, and data governance | Good foundation | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 3.2ms |
| **Q18** | Why did the risk manager or guard prevent a trade? | Risk, system behavior, and data governance | Partial | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 28.2ms |
| **Q19** | What happened during this run, from schedule tick through order execution? | Risk, system behavior, and data governance | Partial — important gap | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 3.9ms |
| **Q20** | What data will expire, what will be retained, and why was a record deleted or skipped? | Risk, system behavior, and data governance | Partial — recently added | 100% | 100% | 100% | 100% | **100.0%** | **PASS** | 3.6ms |

## Category Breakdown

| Category | Passed | Mean Fact Recall | Mean Epistemic | Mean Total |
| :--- | :---: | :---: | :---: | :---: |
| **Live operations and account state** | 4/4 | 100.0% | 100.0% | **100.0%** |
| **Decisions and configuration** | 4/4 | 100.0% | 100.0% | **100.0%** |
| **Performance and attribution** | 4/4 | 100.0% | 100.0% | **100.0%** |
| **Backtesting and experiments** | 4/4 | 100.0% | 100.0% | **100.0%** |
| **Risk, system behavior, and data governance** | 4/4 | 100.0% | 100.0% | **100.0%** |