"""Scores for one run (item level) and for a whole experiment (run level). Deterministic."""

import re
from statistics import mean
from typing import Any, cast

from langfuse.experiment import Evaluation, EvaluatorFunction, RunEvaluatorFunction


def finished(*, output: dict[str, Any], **_: Any) -> Evaluation:
    """Did the run end with run_finished (not failed, not stuck waiting)?"""
    last = output["events"][-1]["type"] if output["events"] else "none"
    return Evaluation(name="finished", value=last == "run_finished", comment=f"last event: {last}")


def has_index(*, output: dict[str, Any], **_: Any) -> Evaluation:
    return Evaluation(name="has_index", value=output["index_html"] is not None)


def site_loads(*, output: dict[str, Any], **_: Any) -> Evaluation:
    """Opened in Chromium: no HTTP error and no console errors."""
    site = output["site"]
    if site is None:
        return Evaluation(name="site_loads", value=False, comment="no index.html")
    problems = ([site["http_error"]] if site["http_error"] else []) + site["errors"]
    return Evaluation(
        name="site_loads",
        value=not problems,
        comment=f"{site['url']}: " + ("; ".join(problems) or "ok"),
    )


def brief_coverage(*, output: dict[str, Any], expected_output: list[str], **_: Any) -> Evaluation:
    """Share of the brief's expected words that appear in the page's visible text."""
    html = output["index_html"] or ""
    text = re.sub(r"<[^>]+>", " ", html).lower()
    found = [word for word in expected_output if word.lower() in text]
    missing = sorted(set(expected_output) - set(found))
    return Evaluation(
        name="brief_coverage",
        value=round(len(found) / len(expected_output), 2) if expected_output else 0.0,
        comment=f"missing: {', '.join(missing) or 'none'}",
    )


def effort(*, output: dict[str, Any], **_: Any) -> list[Evaluation]:
    """How much work it took: delegations and wall-clock time."""
    delegations = sum(1 for e in output["events"] if e["type"] == "task_assigned")
    return [
        Evaluation(name="delegations", value=delegations),
        Evaluation(name="seconds", value=round(output["seconds"], 1)),
    ]


def averages(*, item_results: list[Any], **_: Any) -> list[Evaluation]:
    """Run level: mean of each numeric/boolean item score across the benchmark."""
    by_name: dict[str, list[float]] = {}
    for result in item_results:
        for evaluation in result.evaluations:
            if isinstance(evaluation.value, bool | int | float):
                by_name.setdefault(evaluation.name, []).append(float(evaluation.value))
    return [
        Evaluation(name=f"avg_{name}", value=round(mean(values), 2))
        for name, values in sorted(by_name.items())
    ]


# Typed as Langfuse's protocols: the functions take the keywords they need plus **_,
# which mypy cannot match structurally against the protocols' full signatures.
ITEM_EVALUATORS = cast(
    list[EvaluatorFunction], [finished, has_index, site_loads, brief_coverage, effort]
)
RUN_EVALUATORS = cast(list[RunEvaluatorFunction], [averages])
