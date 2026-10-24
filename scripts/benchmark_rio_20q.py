from __future__ import annotations
# pylint: disable=too-many-locals

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from tests.benchmark.agent_20q.adversarial_scenarios import ADVERSARIAL_QUESTIONS  # pylint: disable=wrong-import-position
from tests.benchmark.agent_20q.evaluator import TwentyQuestionsEvaluator  # pylint: disable=wrong-import-position
from tests.benchmark.agent_20q.models import BenchmarkProvenance  # pylint: disable=wrong-import-position
from tests.benchmark.agent_20q.scenarios import (  # pylint: disable=wrong-import-position
    TWENTY_QUESTIONS,
    build_seeded_environment,
)


def capture_provenance(model_id: str, mode: str, tools: dict[str, Any]) -> BenchmarkProvenance:
    commit = "unknown"
    branch = "unknown"
    dirty = False
    try:
        commit = subprocess.check_output(
            ["git", "-C", str(PROJECT_ROOT), "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        branch = subprocess.check_output(
            ["git", "-C", str(PROJECT_ROOT), "branch", "--show-current"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        status = subprocess.check_output(
            ["git", "-C", str(PROJECT_ROOT), "status", "--porcelain"],
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        dirty = bool(status)
    except Exception:  # pylint: disable=broad-exception-caught
        pass

    tool_manifest = {name: getattr(tool, "name", name) for name, tool in tools.items()}
    return BenchmarkProvenance(
        git_commit=commit,
        git_branch=branch,
        git_dirty=dirty,
        model_id=model_id,
        provider="scripted" if mode == "deterministic" else "live",
        suite_version="2.0-grounded",
        tool_manifest=tool_manifest,
        evaluated_at=datetime.now(timezone.utc).isoformat(),
        python_version=sys.version.split()[0],
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the Rio Grounding & Quality Gate Benchmark Suite."
    )
    parser.add_argument(
        "--mode",
        choices=["deterministic", "live"],
        default="deterministic",
        help="Evaluation mode: 'deterministic' uses scripted mock; 'live' uses configured LLM provider.",
    )
    parser.add_argument(
        "--model-id",
        default="scripted-grounded-v2",
        help="Model identifier recorded in benchmark report.",
    )
    parser.add_argument(
        "--trials",
        type=int,
        default=None,
        help="Number of trials per prompt (default: 1 for deterministic, 3 for live).",
    )
    parser.add_argument(
        "--include-adversarial",
        action="store_true",
        help="Include adversarial missing, stale, and conflicting data scenarios.",
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
        help="Evaluate only the canonical prompt per question instead of all paraphrases.",
    )
    parser.add_argument(
        "--question-ids",
        default=None,
        help="Optional comma-separated list of question IDs to evaluate (e.g. 'Q01,Q02,ADV01').",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional limit on the number of questions to evaluate.",
    )
    parser.add_argument(
        "--delay-seconds",
        type=float,
        default=0.0,
        help="Delay in seconds between prompt evaluations to respect API rate limits.",
    )
    parser.add_argument(
        "--fail-under-score",
        type=float,
        default=0.85,
        help="Minimum overall composite score required for quality gate approval.",
    )
    parser.add_argument(
        "--max-unsupported-claims",
        type=float,
        default=0.0,
        help="Maximum allowable unsupported claims rate for quality gate approval (default 0.0).",
    )
    parser.add_argument(
        "--archive",
        action="store_true",
        help="Automatically archive a timestamped versioned report under docs/benchmarks/reports/.",
    )
    return parser.parse_args()


def main() -> int:  # pylint: disable=too-many-statements
    args = parse_args()
    trials = args.trials if args.trials is not None else (3 if args.mode == "live" else 1)
    env = build_seeded_environment()
    llm_adapter = None

    if args.mode == "live":
        from src.configuration.llm_config import LlmConfig  # pylint: disable=import-outside-toplevel
        from src.llm.model_factory import ModelFactory  # pylint: disable=import-outside-toplevel

        llm_cfg = LlmConfig()
        requested_model = None if args.model_id == "scripted-grounded-v2" else args.model_id
        if requested_model is None and llm_cfg.default_model:
            args.model_id = llm_cfg.default_model.name
        llm_adapter = ModelFactory.create_model(llm_cfg, model_name=requested_model)
        raw_model = getattr(llm_adapter, "_model", None)
        if raw_model is not None and hasattr(raw_model, "max_tokens"):
            raw_model.max_tokens = 800
            setattr(llm_adapter, "_bound_model", raw_model)

    evaluator = TwentyQuestionsEvaluator(
        env=env,
        llm_adapter=llm_adapter,
        mode=args.mode,
        model_id=args.model_id,
    )

    provenance = capture_provenance(model_id=args.model_id, mode=args.mode, tools=env.tools)

    questions = list(TWENTY_QUESTIONS)
    if args.include_adversarial:
        questions.extend(ADVERSARIAL_QUESTIONS)

    if args.question_ids:
        target_ids = {qid.strip().upper() for qid in args.question_ids.split(",") if qid.strip()}
        questions = [q for q in questions if q.question_id.upper() in target_ids]

    if args.limit and args.limit > 0:
        questions = questions[:args.limit]

    delay = args.delay_seconds if args.delay_seconds > 0.0 else (1.5 if args.mode == "live" else 0.0)

    report = evaluator.run_suite(
        questions=questions,
        include_paraphrases=not args.no_paraphrases,
        trials=trials,
        provenance=provenance,
        fail_under_score=args.fail_under_score,
        max_unsupported_rate=args.max_unsupported_claims,
        delay_seconds=delay,
    )

    md_content = report.to_markdown()
    json_data = json.dumps(asdict(report), indent=2, default=str)

    if args.output_md:
        out_md_path = Path(args.output_md)
        out_md_path.parent.mkdir(parents=True, exist_ok=True)
        out_md_path.write_text(md_content, encoding="utf-8")

    if args.output_json:
        out_json_path = Path(args.output_json)
        out_json_path.parent.mkdir(parents=True, exist_ok=True)
        out_json_path.write_text(json_data, encoding="utf-8")

    if args.archive:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        safe_model = args.model_id.replace("/", "_")
        short_commit = provenance.git_commit[:8] if provenance.git_commit else "curr"
        archive_dir = PROJECT_ROOT / "docs" / "benchmarks" / "reports"
        archive_dir.mkdir(parents=True, exist_ok=True)

        archive_md = archive_dir / f"bench_{stamp}_{safe_model}_{short_commit}.md"
        archive_json = archive_dir / f"bench_{stamp}_{safe_model}_{short_commit}.json"
        archive_md.write_text(md_content, encoding="utf-8")
        archive_json.write_text(json_data, encoding="utf-8")
        print(f"Archived report to {archive_md.relative_to(PROJECT_ROOT)}")

    print(md_content)
    return 0 if report.quality_gate_passed else 1


if __name__ == "__main__":
    sys.exit(main())
