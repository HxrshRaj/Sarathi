"""Run an evaluation from the command line (bypasses the API/queue).

python -m worker.evaluation.cli v1 --model claude-sonnet-5 [--baseline <uuid>]
"""

from __future__ import annotations

import argparse
import json
import uuid

from app.config import get_settings
from app.db import SyncSessionLocal
from app.models.enums import EvaluationStatus
from app.models.evaluation import Evaluation

from worker.evaluation.runner import run_evaluation


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a CodePilot benchmark set")
    parser.add_argument("benchmark_set", nargs="?", default="v1")
    parser.add_argument("--model", default=get_settings().llm_default_model)
    parser.add_argument("--prompt-bundle", default="active")
    parser.add_argument("--baseline", default=None)
    parser.add_argument("--comparison-group", default=None)
    args = parser.parse_args()

    with SyncSessionLocal() as db:
        ev = Evaluation(
            benchmark_set=args.benchmark_set,
            model=args.model,
            prompt_bundle=args.prompt_bundle,
            comparison_group=args.comparison_group,
            baseline_evaluation_id=uuid.UUID(args.baseline) if args.baseline else None,
            status=EvaluationStatus.QUEUED,
        )
        db.add(ev)
        db.commit()
        ev_id = str(ev.id)

    summary = run_evaluation(ev_id)
    print(json.dumps({"evaluation_id": ev_id, **summary}, indent=2))


if __name__ == "__main__":
    main()
