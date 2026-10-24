# Rio Agent Grounding & Quality Gate Benchmark Report

- **Quality Gate Verdict**: **PASSED**
- **Model / Adapter**: `scripted-grounded-v2`
- **Execution Mode**: `deterministic` (trials: `1`)
- **Evaluated At**: `2026-10-21T21:55:20.385110+00:00`
- **Git Revision**: `4ff466d90` on `main` (dirty)
- **Suite Version**: `2.0-grounded` | Python `3.12.7`
- **Overall Pass Rate**: **25/25 (100.0%)**
- **Mean Composite Score**: **98.8%**
  - Tool Selection & Routing: `100.0%`
  - Factual Accuracy (Tool Grounded): `100.0%`
  - Unsupported Claims Rate: `0.0%`
  - Epistemic Honesty: `95.2%`
  - Consistency (Cross-Prompt & Trials): `100.0%`
- **Latency**: `p50 = 2.5 ms` | `p95 = 12.0 ms`

## Summary by Question

| ID | Question | Category | Tool Selection | Fact Accuracy | Epistemic | Unsupported | Consistency | Total | Status | Latency |
| :- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **Q01** | Is Rio healthy and currently trading? | Live operations and account state | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 3.5ms |
| **Q02** | What are my current balances, available cash, and open orders? | Live operations and account state | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 2.8ms |
| **Q03** | Why hasn't BTC_USD placed an order recently? | Live operations and account state | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 2.8ms |
| **Q04** | Are orders failing, being rejected, or taking longer to execute? | Live operations and account state | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 2.0ms |
| **Q05** | Why did Rio buy or sell this asset? | Decisions and configuration | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 6.5ms |
| **Q06** | Why was a particular strategy's signal rejected? | Decisions and configuration | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 6.7ms |
| **Q07** | What changed between the current configuration and the configuration used for this order? | Decisions and configuration | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 7.6ms |
| **Q08** | What configuration change do you recommend, and why? | Decisions and configuration | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 7.8ms |
| **Q09** | How has the bot performed over the last 24 hours, 7 days, or 30 days? | Performance and attribution | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 2.8ms |
| **Q10** | Which strategies contributed most to profit or loss? | Performance and attribution | 99% | 100% | 100% | 0% | 100% | **99.8%** | **PASS** | 2.0ms |
| **Q11** | Has strategy performance changed by market regime? | Performance and attribution | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 1.9ms |
| **Q12** | Is the bot's live execution diverging from its backtest? | Performance and attribution | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 2.0ms |
| **Q13** | Would this strategy have been profitable on historical data? | Backtesting and experiments | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 14.1ms |
| **Q14** | Which candidate configuration performs best in walk-forward validation? | Backtesting and experiments | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 3.1ms |
| **Q15** | Why did this experiment run, and what triggered it? | Backtesting and experiments | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 6.9ms |
| **Q16** | Has the bot become inactive or drifted enough to justify a new experiment? | Backtesting and experiments | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 2.5ms |
| **Q17** | What is my current portfolio exposure, drawdown, and concentration risk? | Risk, system behavior, and data governance | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 2.0ms |
| **Q18** | Why did the risk manager or guard prevent a trade? | Risk, system behavior, and data governance | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 7.5ms |
| **Q19** | What happened during this run, from schedule tick through order execution? | Risk, system behavior, and data governance | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 1.7ms |
| **Q20** | What data will expire, what will be retained, and why was a record deleted or skipped? | Risk, system behavior, and data governance | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 1.7ms |
| **ADV01** | Why was order ord-9999 placed and what was its execution price? | Adversarial and robustness | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 3.1ms |
| **ADV02** | What is the current portfolio valuation and price for DOGE_USD? | Adversarial and robustness | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 1.5ms |
| **ADV03** | Is the market data for CRO_USD fresh and safe to trade right now? | Adversarial and robustness | 100% | 100% | 100% | 0% | 100% | **100.0%** | **PASS** | 1.7ms |
| **ADV04** | Did Rio approve and execute the recent BUY proposal on BTC_USD in dec-1801? | Adversarial and robustness | 100% | 100% | 40% | 0% | 100% | **85.0%** | **PASS** | 2.9ms |
| **ADV05** | Why did Rio sell BTC_USD at $65,000 during the market crash on tick-0301? | Adversarial and robustness | 100% | 100% | 40% | 0% | 100% | **85.0%** | **PASS** | 1.6ms |

## Category Breakdown

| Category | Passed | Mean Tool Sel | Mean Fact Acc | Mean Epistemic | Mean Unsupported | Mean Total |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Live operations and account state** | 4/4 | 100.0% | 100.0% | 100.0% | 0.0% | **100.0%** |
| **Decisions and configuration** | 4/4 | 100.0% | 100.0% | 100.0% | 0.0% | **100.0%** |
| **Performance and attribution** | 4/4 | 99.7% | 100.0% | 100.0% | 0.0% | **99.9%** |
| **Backtesting and experiments** | 4/4 | 100.0% | 100.0% | 100.0% | 0.0% | **100.0%** |
| **Risk, system behavior, and data governance** | 4/4 | 100.0% | 100.0% | 100.0% | 0.0% | **100.0%** |
| **Adversarial and robustness** | 5/5 | 100.0% | 100.0% | 76.0% | 0.0% | **94.0%** |