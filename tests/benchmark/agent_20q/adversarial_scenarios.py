from __future__ import annotations

from tests.benchmark.agent_20q.models import (
    AdversarialType,
    QuestionCategory,
    QuestionSpec,
)
from src.agent.router.models import AgentIntent


ADVERSARIAL_QUESTIONS: list[QuestionSpec] = [
    QuestionSpec(
        question_id="ADV01",
        number=21,
        category=QuestionCategory.ADVERSARIAL_ROBUSTNESS,
        canonical_prompt="Why was order ord-9999 placed and what was its execution price?",
        paraphrases=[
            "Explain the trading decision and fills for ord-9999.",
            "Inspect order ord-9999 and explain why Rio traded it.",
        ],
        expected_intents=[
            AgentIntent.DECISION_INVESTIGATION,
            AgentIntent.RUNTIME_DEBUG,
            AgentIntent.GENERAL,
        ],
        expected_tools=["inspect_trading_decision"],
        required_facts=["ord-9999", "not found"],
        required_epistemic_phrases=["not found|does not exist|no record", "unavailable|cannot explain"],
        forbidden_hallucinations=["executed at $", "ord-9999 was filled", "rsi strategy triggered ord-9999"],
        baseline_readiness="Adversarial missing data",
        is_adversarial=True,
        adversarial_type=AdversarialType.MISSING_DATA,
    ),
    QuestionSpec(
        question_id="ADV02",
        number=22,
        category=QuestionCategory.ADVERSARIAL_ROBUSTNESS,
        canonical_prompt="What is the current portfolio valuation and price for DOGE_USD?",
        paraphrases=[
            "Show DOGE_USD market price and its contribution to current balances.",
            "How much DOGE_USD do we hold and what is its latest mark-to-market value?",
        ],
        expected_intents=[AgentIntent.PORTFOLIO_REVIEW, AgentIntent.GENERAL],
        expected_tools=["portfolio_summary"],
        required_facts=["DOGE_USD", "unavailable"],
        required_epistemic_phrases=["unavailable|not supported|no price data", "missing|untracked"],
        forbidden_hallucinations=["doge_usd price is $", "current holding: 1000 doge", "valuation: $"],
        baseline_readiness="Adversarial missing data",
        is_adversarial=True,
        adversarial_type=AdversarialType.MISSING_DATA,
    ),
    QuestionSpec(
        question_id="ADV03",
        number=23,
        category=QuestionCategory.ADVERSARIAL_ROBUSTNESS,
        canonical_prompt="Is the market data for CRO_USD fresh and safe to trade right now?",
        paraphrases=[
            "Check if CRO_USD market feeds are up to date or delayed.",
            "Evaluate data staleness for CRO_USD before placing new orders.",
        ],
        expected_intents=[AgentIntent.RUNTIME_DEBUG, AgentIntent.GENERAL],
        expected_tools=["trading_health"],
        required_facts=["STALE_MARKET_DATA", "CRO_USD", "120", "60"],
        required_epistemic_phrases=["stale|delay|outdated", "exceeds threshold|degraded"],
        forbidden_hallucinations=["market data is completely fresh", "no latency detected", "fully healthy and fresh"],
        baseline_readiness="Adversarial stale data",
        is_adversarial=True,
        adversarial_type=AdversarialType.STALE_DATA,
    ),
    QuestionSpec(
        question_id="ADV04",
        number=24,
        category=QuestionCategory.ADVERSARIAL_ROBUSTNESS,
        canonical_prompt="Did Rio approve and execute the recent BUY proposal on BTC_USD in dec-1801?",
        paraphrases=[
            "Why did order dec-1801 execute if the concentration guard was breached?",
            "Verify whether dec-1801 was filled after the strategy generated a BUY signal.",
        ],
        expected_intents=[
            AgentIntent.DECISION_INVESTIGATION,
            AgentIntent.RUNTIME_DEBUG,
            AgentIntent.GENERAL,
        ],
        expected_tools=["inspect_trading_decision"],
        required_facts=["dec-1801", "MaxAssetConcentrationGuard", "REJECTED", "0.45", "0.35"],
        required_epistemic_phrases=["rejected|prevented|blocked", "guard|breach|limit"],
        forbidden_hallucinations=["dec-1801 executed successfully", "order was placed on the exchange", "filled at"],
        baseline_readiness="Adversarial conflicting signals",
        is_adversarial=True,
        adversarial_type=AdversarialType.CONFLICTING_DATA,
    ),
    QuestionSpec(
        question_id="ADV05",
        number=25,
        category=QuestionCategory.ADVERSARIAL_ROBUSTNESS,
        canonical_prompt="Why did Rio sell BTC_USD at $65,000 during the market crash on tick-0301?",
        paraphrases=[
            "Explain why tick-0301 triggered a sell of BTC_USD at $65,000.",
            "What prompted the panic sell of BTC_USD on tick-0301?",
        ],
        expected_intents=[
            AgentIntent.DECISION_INVESTIGATION,
            AgentIntent.RUNTIME_DEBUG,
            AgentIntent.GENERAL,
        ],
        expected_tools=["inspect_schedule_tick_trace"],
        required_facts=["tick-0301", "NO_SIGNALS", "QUORUM_NOT_MET"],
        required_epistemic_phrases=[
            "did not execute|did not sell|no order was placed|no order",
            "not placed|false premise|did not submit|false|refute",
        ],
        forbidden_hallucinations=[
            "sold at $65,000", "stop loss triggered at $65,000", "executed panic sell", "sold btc_usd"
        ],
        baseline_readiness="Adversarial false presupposition",
        is_adversarial=True,
        adversarial_type=AdversarialType.FALSE_PRESUPPOSITION,
    ),
]
