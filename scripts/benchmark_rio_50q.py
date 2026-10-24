from __future__ import annotations
# pylint: disable=too-many-locals,too-many-statements

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.benchmark.agent_50q.evaluator import FiftyQuestionsEvaluator  # pylint: disable=wrong-import-position
from tests.benchmark.agent_50q.scenarios import FIFTY_QUESTIONS  # pylint: disable=wrong-import-position


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Rio 50-Question Agent Graph Quality & Regression Evaluation Suite."
    )
    parser.add_argument(
        "--mode",
        choices=["deterministic", "live", "live-http"],
        default="deterministic",
        help="Evaluation mode: deterministic, live (in-process gateway), or live-http (running API).",
    )
    parser.add_argument(
        "--target",
        default="http://127.0.0.1:8000/api/v1/chat",
        help="Target HTTP endpoint when running with --mode live-http.",
    )
    parser.add_argument(
        "--model-id",
        default=None,
        help="Model identifier recorded in report.",
    )
    parser.add_argument(
        "--question-ids",
        default=None,
        help="Comma-separated question IDs to evaluate (e.g. 'Q01,Q06,Q11,Q23').",
    )
    parser.add_argument(
        "--category",
        default=None,
        help="Filter evaluation to a specific category substring (e.g. 'Category 1', 'Backtest').",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit the number of questions to evaluate.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=None,
        help="Delay in seconds between questions (default: 0.0 for deterministic, 1.5 for live).",
    )
    parser.add_argument(
        "--fail-under-score",
        type=float,
        default=0.80,
        help="Minimum overall composite score required for release gate (default 0.80).",
    )
    parser.add_argument(
        "--output-md",
        default=None,
        help="Optional path to write the Markdown evaluation scorecard.",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional path to write the JSON evaluation results.",
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Archive timestamped scorecard to docs/benchmarks/reports/.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    model_id = args.model_id or ("scripted-grounded-50q" if args.mode == "deterministic" else "live-agent")
    llm_adapter = None

    if args.mode == "live":
        from src.configuration.llm_config import LlmConfig  # pylint: disable=import-outside-toplevel
        from src.llm.model_factory import ModelFactory  # pylint: disable=import-outside-toplevel

        llm_cfg = LlmConfig()
        if args.model_id is None and llm_cfg.default_model:
            model_id = llm_cfg.default_model.name
        llm_adapter = ModelFactory.create_model(llm_cfg, model_name=args.model_id)
        raw_model = getattr(llm_adapter, "_model", None)
        if raw_model is not None and hasattr(raw_model, "max_tokens"):
            raw_model.max_tokens = 800
            setattr(llm_adapter, "_bound_model", raw_model)

    evaluator = FiftyQuestionsEvaluator(
        llm_adapter=llm_adapter,
        mode="live_http" if args.mode == "live-http" else args.mode,
        model_id=model_id,
        target_endpoint=args.target if args.mode == "live-http" else None,
    )

    questions = list(FIFTY_QUESTIONS)
    if args.category:
        cat_lower = args.category.lower()
        questions = [q for q in questions if cat_lower in q.category.value.lower()]

    if args.question_ids:
        target_ids = {qid.strip().upper() for qid in args.question_ids.split(",") if qid.strip()}
        questions = [q for q in questions if q.question_id.upper() in target_ids]

    if args.limit and args.limit > 0:
        questions = questions[:args.limit]

    default_delay = 1.5 if args.mode in ("live", "live-http") else 0.0
    delay = args.delay_seconds if args.delay_seconds is not None else default_delay

    report = evaluator.run_suite(
        questions=questions,
        delay_seconds=delay,
        fail_under_score=args.fail_under_score,
    )

    md_content = report.to_markdown()
    json_data = json.dumps(
        {
            "evaluated_at": report.evaluated_at,
            "mode": report.mode,
            "model_id": report.model_id,
            "target_endpoint": report.target_endpoint,
            "total_questions": report.total_questions,
            "passed_questions": report.passed_questions,
            "overall_score": report.overall_score,
            "critical_gates_passed": report.critical_gates_passed,
            "interpretation_band": report.interpretation_band,
            "category_scores": report.category_scores,
            "dimension_scores": report.dimension_scores,
            "question_scores": [q.to_dict() for q in report.question_scores],
        },
        indent=2,
    )

    if args.output_md:
        out_md = Path(args.output_md)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        out_md.write_text(md_content, encoding="utf-8")

    if args.output_json:
        out_json = Path(args.output_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json_data, encoding="utf-8")

    if args.archive:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        archive_dir = PROJECT_ROOT / "docs" / "benchmarks" / "reports"
        archive_dir.mkdir(parents=True, exist_ok=True)
        archive_md = archive_dir / f"bench_50q_{stamp}_{args.mode}.md"
        archive_json = archive_dir / f"bench_50q_{stamp}_{args.mode}.json"
        archive_md.write_text(md_content, encoding="utf-8")
        archive_json.write_text(json_data, encoding="utf-8")
        print(f"Archived report to {archive_md.relative_to(PROJECT_ROOT)}")

    print(md_content)
    return 0 if (report.critical_gates_passed and report.overall_score >= args.fail_under_score) else 1


if __name__ == "__main__":
    sys.exit(main())
