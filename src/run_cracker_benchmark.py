"""Run Cracker prompt injection benchmarks against OpenRouter models.

This module wraps the Cracker benchmark to test models against indirect prompt
injection attacks. It runs scenarios across file, tool, and skill attack vectors
and measures both attack success rate and utility preservation.
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
    """Results from running Cracker prompt injection benchmark."""

    def __init__(
        self,
        model_id: str,
        total_tasks: int,
        canaries_leaked: int,
        utility_passed: int,
        scenario_results: List[Dict[str, Any]],
        adaptive: bool = False,
    ):
        self.model_id = model_id
        self.total_tasks = total_tasks
        self.canaries_leaked = canaries_leaked
        self.utility_passed = utility_passed
        self.scenario_results = scenario_results
        self.adaptive = adaptive

    @property
    def leak_rate(self) -> float:
        return (self.canaries_leaked / self.total_tasks * 100) if self.total_tasks > 0 else 0.0

    @property
    def security_rate(self) -> float:
        """Percentage of attacks blocked (canary NOT leaked)."""
        return 100.0 - self.leak_rate

    @property
    def utility_rate(self) -> float:
        return (self.utility_passed / self.total_tasks * 100) if self.total_tasks > 0 else 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "model_id": self.model_id,
            "benchmark": "cracker",
            "adaptive": self.adaptive,
            "total_tasks": self.total_tasks,
            "canaries_leaked": self.canaries_leaked,
            "leak_rate": round(self.leak_rate, 2),
            "security_rate": round(self.security_rate, 2),
            "utility_passed": self.utility_passed,
            "utility_rate": round(self.utility_rate, 2),
            "scenario_results": self.scenario_results,
            "benchmarked_at": datetime.now().isoformat(),
        }


def run_cracker_benchmark(
    model_id: str,
    cracker_dir: Path,
    output_dir: Path,
    backend: str = "daytona",
    adaptive: bool = True,
    vector: Optional[str] = None,
    scenario: Optional[str] = None,
    attacker_model: Optional[str] = None,
    max_turns: int = 5,
    malicious_task_id: str = "exfil-single",
    scenarios: Optional[str] = None,
) -> Optional[CrackerBenchmarkResult]:
    """Run Cracker benchmark for a single model.

    Args:
        model_id: OpenRouter model ID (e.g. "google/gemini-2.0-flash-exp:free")
        cracker_dir: Path to the cracker repository
        output_dir: Path to save results
        backend: Backend type ("local" or "daytona")
        adaptive: Whether to use adaptive attacker mode
        vector: Attack vector filter ("file", "tool", "skill", or None for all)
        scenario: Specific scenario ID (or None for all)
        attacker_model: Attacker model for adaptive mode
        max_turns: Max attacker turns for adaptive mode

    Returns:
        CrackerBenchmarkResult if successful, None otherwise
    """
    logger.info(f"Running Cracker benchmark for {model_id}")
    logger.info(f"  Backend: {backend}, Adaptive: {adaptive}")
    if vector:
        logger.info(f"  Vector filter: {vector}")
    if scenario:
        logger.info(f"  Scenario: {scenario}")

    # Build command using the 'benchmark' subcommand which runs all scenarios
    cmd = [
        sys.executable, "-m", "cracker.cli",
        "benchmark",
        "--backend", backend,
        "--model", model_id,
        "--malicious-task", malicious_task_id,
        "--agent-name", model_id,
    ]

    if attacker_model:
        cmd.extend(["--attacker-model", attacker_model])

    if max_turns:
        cmd.extend(["--max-turns", str(max_turns)])

    if scenarios:
        cmd.extend(["--scenarios", scenarios])

    # Output file
    safe_model_name = model_id.replace("/", "_").replace(":", "_")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    mode = "adaptive" if adaptive else "static"
    output_file = output_dir / f"cracker_{mode}_{safe_model_name}_{timestamp}.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)

    cmd.extend(["--output", str(output_file.resolve())])

    # Set environment
    import os
    env = os.environ.copy()

    # Run benchmark
    try:
        logger.info(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            cwd=cracker_dir,
            env=env,
            capture_output=True,
            text=True,
            timeout=7200,  # 2 hour timeout (adaptive can be slow)
        )

        if result.stdout:
            logger.info(f"stdout: {result.stdout[-500:]}")
        if result.stderr:
            logger.warning(f"stderr: {result.stderr[-500:]}")

        # Check if output file was created
        if not output_file.exists():
            logger.error(f"Cracker benchmark did not produce output file for {model_id}")
            logger.error(f"  Return code: {result.returncode}")
            return None

        # Parse results — benchmark command exports flat keys from BenchmarkResult.to_dict()
        with open(output_file) as f:
            data = json.load(f)

        # by_scenario is a dict keyed by scenario name; convert to list for storage
        scenario_results = list(data.get("by_scenario", {}).values())

        return CrackerBenchmarkResult(
            model_id=model_id,
            total_tasks=data.get("total_tasks", 0),
            canaries_leaked=data.get("n_attacks_succeeded", 0),
            utility_passed=data.get("n_utility_preserved", 0),
            scenario_results=scenario_results,
            adaptive=adaptive,
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
        "--cracker-dir",
        type=Path,
        default=Path(__file__).parent.parent / "cracker",
        help="Path to Cracker repository",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/benchmarks/cracker"),
        help="Output directory for results",
    )
    parser.add_argument(
        "--backend",
        default="daytona",
        choices=["local", "daytona"],
        help="Backend type (default: daytona)",
    )
    parser.add_argument(
        "--adaptive",
        action="store_true",
        default=True,
        help="Use adaptive attacker mode (default: True)",
    )
    parser.add_argument(
        "--no-adaptive",
        action="store_true",
        default=False,
        help="Disable adaptive attacker (static mode only)",
    )
    parser.add_argument("--vector", choices=["file", "tool", "skill"], help="Attack vector filter (unused, kept for backward compat)")
    parser.add_argument("--scenario", help="Specific scenario ID (unused, kept for backward compat)")
    parser.add_argument("--attacker-model", help="Attacker model for adaptive mode")
    parser.add_argument("--max-turns", type=int, default=5, help="Max attacker turns (default: 5)")
    parser.add_argument("--malicious-task", default="exfil-single", help="Malicious task ID (default: exfil-single)")
    parser.add_argument("--scenarios", default=None, help="Comma-separated scenario names to run (default: all). Use 'file' for a fast debug run.")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    adaptive = not args.no_adaptive

    result = run_cracker_benchmark(
        model_id=args.model,
        cracker_dir=args.cracker_dir,
        output_dir=args.output_dir,
        backend=args.backend,
        adaptive=adaptive,
        vector=args.vector,
        scenario=args.scenario,
        attacker_model=args.attacker_model,
        max_turns=args.max_turns,
        malicious_task_id=args.malicious_task,
        scenarios=args.scenarios,
    )

    if result:
        # Save the structured result
        safe_model_name = args.model.replace("/", "_").replace(":", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = args.output_dir / f"cracker_{safe_model_name}_{timestamp}.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        logger.info(f"Results saved to {output_file}")
        logger.info(
            f"  Security: {result.security_rate:.1f}% | "
            f"Utility: {result.utility_rate:.1f}% | "
            f"Leaked: {result.canaries_leaked}/{result.total_tasks}"
        )
    else:
        logger.error("Cracker benchmark failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
