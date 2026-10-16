from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.benchmark.agent_20q.evaluator import TwentyQuestionsEvaluator  # pylint: disable=wrong-import-position
from tests.benchmark.agent_20q.scenarios import build_seeded_environment  # pylint: disable=wrong-import-position


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Rio 20-Question Acceptance & Grounding Benchmark Suite."
    )
    parser.add_argument(
        "--mode",
        choices=["deterministic", "live"],
        default="deterministic",
        help="Evaluation mode: 'deterministic' uses ScriptedGroundedLlmAdapter; 'live' uses configured LLM provider.",
    )
    parser.add_argument(
        "--model-id",
        default="scripted-grounded-v1",
        help="Model identifier recorded in benchmark report.",
    )
    parser.add_argument(
        "--output-md",
        default=None,
        help="Optional path to write the Markdown benchmark report.",
    )
    parser.add_argument(
        "--output-json",
        default=None,
        help="Optional path to write the JSON benchmark report.",
    )
    parser.add_argument(
        "--no-paraphrases",
        action="store_true",
        help="Evaluate only the canonical prompt per question instead of all 3 paraphrases.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    env = build_seeded_environment()
    llm_adapter = None

    if args.mode == "live":
        from src.configuration.llm_config import LlmConfig  # pylint: disable=import-outside-toplevel
        from src.llm.model_factory import ModelFactory  # pylint: disable=import-outside-toplevel

        llm_adapter = ModelFactory.create_model(LlmConfig.load(), model_name=args.model_id)

    evaluator = TwentyQuestionsEvaluator(
        env=env,
        llm_adapter=llm_adapter,
        mode=args.mode,
        model_id=args.model_id,
    )
    report = evaluator.run_suite(include_paraphrases=not args.no_paraphrases)
    md_content = report.to_markdown()

    if args.output_md:
        out_md_path = Path(args.output_md)
        out_md_path.parent.mkdir(parents=True, exist_ok=True)
        out_md_path.write_text(md_content, encoding="utf-8")

    if args.output_json:
        out_json_path = Path(args.output_json)
        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        out_json_path.write_text(
            json.dumps(asdict(report), indent=2),
            encoding="utf-8",
        )

    print(md_content)
    return 0 if report.passed_questions == report.total_questions else 1


if __name__ == "__main__":
    sys.exit(main())
