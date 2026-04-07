#!/usr/bin/env python3
"""Pick the best free OpenRouter models from the benchmark CI leaderboard.

Usage:
    python3 src/pick_free_models.py
    python3 src/pick_free_models.py --top 10 --sort security
    python3 src/pick_free_models.py --sort balanced --json
    python3 src/pick_free_models.py --min-score 40
"""

import argparse
import json
import sys
import urllib.request
from typing import Any

LEADERBOARD_URL = "https://sequrity-ai.github.io/benchmarked-free-ride-ci/api/leaderboard.json"


def fetch_leaderboard() -> list[dict[str, Any]]:
    """Fetch the leaderboard JSON from GitHub Pages."""
    try:
        with urllib.request.urlopen(LEADERBOARD_URL, timeout=15) as resp:
            data = json.loads(resp.read())
        return data.get("leaderboard", [])
    except Exception as e:
        print(f"Error fetching leaderboard: {e}", file=sys.stderr)
        sys.exit(1)


def filter_free_models(
    leaderboard: list[dict[str, Any]],
    min_score: float | None = None,
) -> list[dict[str, Any]]:
    """Filter to benchmarked free models."""
    models = [
        m for m in leaderboard
        if ":free" in m.get("model_id", "")
        and m.get("is_benchmarked", False)
    ]
    if min_score is not None:
        models = [m for m in models if (m.get("composite_score") or 0) >= min_score]
    return models


def _speed_score(m: dict[str, Any]) -> float:
    latency = m.get("avg_latency_seconds")
    if latency is None:
        return 50.0
    return max(0.0, 100.0 - min(latency * 2, 100.0))


def balanced_score(m: dict[str, Any]) -> float:
    utility = (m.get("composite_score") or 0) * 0.5
    security = (m.get("cracker_security_rate") if m.get("cracker_security_rate") is not None else 50.0) * 0.3
    speed = _speed_score(m) * 0.2
    return utility + security + speed


def sort_models(
    models: list[dict[str, Any]],
    sort_by: str,
) -> list[dict[str, Any]]:
    """Sort models by the given criterion."""
    if sort_by == "score":
        return sorted(models, key=lambda m: m.get("composite_score") or 0, reverse=True)
    elif sort_by == "security":
        return sorted(
            models,
            key=lambda m: m.get("cracker_security_rate") if m.get("cracker_security_rate") is not None else -1,
            reverse=True,
        )
    elif sort_by == "fast":
        return sorted(
            models,
            key=lambda m: m.get("avg_latency_seconds") if m.get("avg_latency_seconds") is not None else float("inf"),
        )
    elif sort_by == "balanced":
        return sorted(models, key=balanced_score, reverse=True)
    else:
        raise ValueError(f"Unknown sort mode: {sort_by}")


def format_context(ctx: int | None) -> str:
    if ctx is None:
        return "n/a"
    if ctx >= 1_000_000:
        return f"{ctx // 1_000_000}M"
    if ctx >= 1_000:
        return f"{ctx // 1_000}K"
    return str(ctx)


def print_human(models: list[dict[str, Any]], sort_by: str) -> None:
    sort_labels = {
        "score": "utility score",
        "security": "security rate",
        "fast": "latency",
        "balanced": "balanced score",
    }
    print(f"\nTop {len(models)} free models (sorted by {sort_labels.get(sort_by, sort_by)}):\n")
    for i, m in enumerate(models, 1):
        model_id = m.get("model_id", "unknown")
        score = m.get("composite_score")
        security = m.get("cracker_security_rate")
        latency = m.get("avg_latency_seconds")
        ctx = m.get("context_length")

        score_str = f"{score:.1f}" if score is not None else "n/a"
        security_str = f"{security:.1f}%" if security is not None else "n/a"
        latency_str = f"{latency:.1f}s" if latency is not None else "n/a"
        ctx_str = format_context(ctx)

        if sort_by == "balanced":
            bal = balanced_score(m)
            print(f"{i}. {model_id}")
            print(f"   Balanced: {bal:.1f} | Score: {score_str} | Security: {security_str} | Latency: {latency_str} | Context: {ctx_str}")
        else:
            print(f"{i}. {model_id}")
            print(f"   Score: {score_str} | Security: {security_str} | Latency: {latency_str} | Context: {ctx_str}")
        print()


def print_json_output(models: list[dict[str, Any]]) -> None:
    output = [
        {
            "model_id": m.get("model_id"),
            "composite_score": m.get("composite_score"),
            "cracker_security_rate": m.get("cracker_security_rate"),
            "cracker_utility_rate": m.get("cracker_utility_rate"),
            "avg_latency_seconds": m.get("avg_latency_seconds"),
            "context_length": m.get("context_length"),
            "quality_score": m.get("quality_score"),
        }
        for m in models
    ]
    print(json.dumps(output, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pick the best free OpenRouter models from benchmark CI results.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--top", type=int, default=5, help="Number of models to show (default: 5)")
    parser.add_argument(
        "--sort",
        choices=["score", "security", "fast", "balanced"],
        default="score",
        help="Sort criterion: score (default), security, fast, balanced",
    )
    parser.add_argument("--json", action="store_true", help="Output as JSON array")
    parser.add_argument("--min-score", type=float, default=None, help="Minimum composite_score threshold")

    args = parser.parse_args()

    leaderboard = fetch_leaderboard()
    models = filter_free_models(leaderboard, min_score=args.min_score)

    if not models:
        print("No benchmarked free models found in leaderboard.", file=sys.stderr)
        sys.exit(1)

    models = sort_models(models, args.sort)
    models = models[: args.top]

    if args.json:
        print_json_output(models)
    else:
        print_human(models, args.sort)


if __name__ == "__main__":
    main()
