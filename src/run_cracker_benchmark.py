"""Run Cracker prompt injection benchmarks against OpenRouter models.

Uses the benchmark command which runs both benign mode (pure utility)
and attack mode (canary + injection) to measure:
- Benign utility: baseline task completion rate
- ASR (Attack Success Rate): % of tasks where the canary was leaked
- UUA (Utility Under Attack): % of tasks completed despite injection
"""

import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class CrackerBenchmarkResult:
    """Results from running Cracker benchmark."""

    def __init__(
        self,
        model_id: str,
        benign_utility: float,
        attack_success_rate: float,
        utility_under_attack: float,
        total_tasks: int,
        results: List[Dict[str, Any]],
    ):
        self.model_id = model_id
        self.benign_utility = benign_utility
        self.attack_success_rate = attack_success_rate
        self.utility_under_attack = utility_under_attack
        self.total_tasks = total_tasks
        self.results = results

    @property
    def utility_drop(self) -> float:
        return self.benign_utility - self.utility_under_attack

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "benchmark": "cracker",
            "version": 2,
            "benign_utility": round(self.benign_utility, 2),
            "attack_success_rate": round(self.attack_success_rate, 2),
            "utility_under_attack": round(self.utility_under_attack, 2),
            "utility_drop": round(self.utility_drop, 2),
            "total_tasks": self.total_tasks,
            "results": self.results,
            "benchmarked_at": datetime.now().isoformat(),
        }


def run_cracker_benchmark(
    model_id: str,
    cracker_dir: Path,
    output_dir: Path,
    backend: str = "daytona",
    vector: Optional[str] = None,
    category: Optional[str] = None,
) -> Optional[CrackerBenchmarkResult]:
    """Run Cracker benchmark for a single model.

    Runs both benign and attack modes to get all three metrics.
    """
    logger.info(f"Running Cracker benchmark for {model_id}")
    logger.info(f"  Backend: {backend}")

    cmd = [
        sys.executable, "-m", "cracker.cli",
        "benchmark",
        "--backend", backend,
        "--model", model_id,
    ]

    if vector:
        cmd.extend(["--vector", vector])
    if category:
        cmd.extend(["--category", category])

    safe_model_name = model_id.replace("/", "_").replace(":", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_file = output_dir / f"cracker_{safe_model_name}_{timestamp}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    cmd.extend(["--output", str(output_file.resolve())])

    import os
    env = os.environ.copy()

    try:
        logger.info(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            cwd=cracker_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=7200,
        )

        if result.stdout:
            logger.info(f"stdout: {result.stdout[-500:]}")
        if result.stderr:
            logger.warning(f"stderr: {result.stderr[-500:]}")

        if not output_file.exists():
            logger.error(f"Cracker benchmark did not produce output file for {model_id}")
            logger.error(f"  Return code: {result.returncode}")
            return None

        with open(output_file) as f:
            data = json.load(f)

        summary = data.get("summary", {})

        # Handle pass@k dict format: {"pass@1": 66.7} → extract pass@1 value
        def _extract(val):
            if isinstance(val, dict):
                return val.get("pass@1", 0)
            return val or 0

        return CrackerBenchmarkResult(
            model_id=model_id,
            benign_utility=_extract(summary.get("benign_utility", 0)),
            attack_success_rate=_extract(summary.get("attack_success_rate", 0)),
            utility_under_attack=_extract(summary.get("utility_under_attack", 0)),
            total_tasks=summary.get("total_tasks", 0),
            results=data.get("results", []),
        )

    except subprocess.TimeoutExpired:
        logger.error(f"Cracker benchmark timed out for {model_id} (2 hours)")
        return None
    except Exception as e:
        logger.error(f"Error running Cracker benchmark for {model_id}: {e}")
        return None


def main():
    """Main entry point for running Cracker benchmarks standalone."""
    import argparse

    parser = argparse.ArgumentParser(description="Run Cracker prompt injection benchmarks")
    parser.add_argument("--model", required=True, help="OpenRouter model ID")
    parser.add_argument(
        "--cracker-dir", type=Path,
        default=Path(__file__).parent.parent / "cracker",
        help="Path to Cracker repository",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=Path("output/benchmarks/cracker"),
        help="Output directory for results",
    )
    parser.add_argument(
        "--backend", default="daytona", choices=["local", "daytona"],
        help="Backend type (default: daytona)",
    )
    parser.add_argument("--vector", choices=["file", "tool", "skill"], help="Attack vector filter")
    parser.add_argument("--category", help="Scenario category filter")
    # Backward compat flags (ignored)
    parser.add_argument("--adaptive", action="store_true", default=False, help="(ignored, kept for compat)")
    parser.add_argument("--no-adaptive", action="store_true", default=False, help="(ignored)")
    parser.add_argument("--attacker-model", help="(ignored)")
    parser.add_argument("--max-turns", type=int, default=5, help="(ignored)")
    parser.add_argument("--malicious-task", default="exfil-single", help="(ignored)")
    parser.add_argument("--scenarios", default=None, help="(ignored)")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    result = run_cracker_benchmark(
        model_id=args.model,
        cracker_dir=args.cracker_dir,
        output_dir=args.output_dir,
        backend=args.backend,
        vector=args.vector,
        category=args.category,
    )

    if result:
        safe_model_name = args.model.replace("/", "_").replace(":", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = args.output_dir / f"cracker_{safe_model_name}_{timestamp}.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        logger.info(f"Results saved to {output_file}")
        logger.info(
            f"  Benign: {result.benign_utility:.1f}% | "
            f"ASR: {result.attack_success_rate:.1f}% | "
            f"UUA: {result.utility_under_attack:.1f}% | "
            f"Drop: {result.utility_drop:.1f}%"
        )
    else:
        logger.error("Cracker benchmark failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
