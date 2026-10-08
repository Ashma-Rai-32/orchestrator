"""CLI: run benchmark briefs against one configuration and write a Markdown report.

uv run python -m staffroom_experiments fake-duo
uv run python -m staffroom_experiments flash-lite-duo --only coffee-landing
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from langfuse import get_client
from langfuse.experiment import ExperimentItem

from staffroom_api.observability import init_tracing, shutdown_tracing
from staffroom_api.settings import Settings
from staffroom_experiments.evaluators import ITEM_EVALUATORS, RUN_EVALUATORS
from staffroom_experiments.harness import load_benchmarks, load_configs, run_brief

RESULTS = Path(__file__).resolve().parents[2] / "results"


def main() -> int:
    configs = load_configs()
    parser = argparse.ArgumentParser(prog="staffroom_experiments")
    parser.add_argument("config", choices=sorted(configs))
    parser.add_argument("--only", nargs="*", help="benchmark keys (default: all)")
    args = parser.parse_args()
    config = configs[args.config]

    settings = Settings()
    if not init_tracing(settings):
        print("Langfuse keys not set: start `docker compose --profile observability up -d`.")
        return 1

    async def task(*, item: ExperimentItem, **_: dict[str, Any]) -> dict[str, Any]:
        goal = item["input"] if isinstance(item, dict) else item.input
        return await run_brief(config, goal, settings.sandbox_image, tracing=True)

    result = get_client().run_experiment(
        name=f"staffroom/{config.name}",
        description=config.description,
        data=load_benchmarks(args.only),
        task=task,
        evaluators=ITEM_EVALUATORS,
        run_evaluators=RUN_EVALUATORS,
        max_concurrency=1,  # one sandbox at a time; free-tier quotas
        metadata={"config": config.name, "model": config.model},
    )
    report = write_report(config.name, config.model, result)
    shutdown_tracing()
    print(result.format())
    print(f"\nreport: {report}")
    return 0


def write_report(config: str, model: str, result: Any) -> Path:
    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    path = RESULTS / f"{stamp}-{config}.md"
    names = sorted({e.name for r in result.item_results for e in r.evaluations})
    lines = [
        f"# {config} ({model}), {stamp} UTC",
        "",
        "| benchmark | " + " | ".join(names) + " |",
        "|---|" + "---|" * len(names),
    ]
    for item in result.item_results:
        scores = {e.name: e.value for e in item.evaluations}
        key = item.item["metadata"]["benchmark"]
        lines.append(f"| {key} | " + " | ".join(str(scores.get(n, "")) for n in names) + " |")
    lines += [
        "",
        "**Run averages:** " + ", ".join(f"{e.name}={e.value}" for e in result.run_evaluations),
    ]
    path.write_text("\n".join(lines) + "\n")
    return path


if __name__ == "__main__":
    sys.exit(main())
