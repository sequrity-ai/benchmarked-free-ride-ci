"""Run AgentDojo safety benchmarks for prompt injection testing.

This module wraps AgentDojo to test OpenRouter models against prompt injection attacks.
Only runs the 'workspace' suite with 'tool_knowledge' attack for efficiency.
"""

import json
import logging
import random
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SafetyBenchmarkResult:
    """Results from running AgentDojo safety benchmark."""

    def __init__(
        self,
        model_id: str,
        avg_utility: float,
        avg_security: float,
        total_user_tasks: int,
        passed_user_tasks: int,
        total_injection_tasks: int,
        passed_injection_tasks: int,
        benchmark_version: str = "v1.2.2",
    ):
        self.model_id = model_id
        self.avg_utility = avg_utility
        self.avg_security = avg_security
        self.total_user_tasks = total_user_tasks
        self.passed_user_tasks = passed_user_tasks
        self.total_injection_tasks = total_injection_tasks
        self.passed_injection_tasks = passed_injection_tasks
        self.benchmark_version = benchmark_version

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "model_id": self.model_id,
            "avg_utility": self.avg_utility,
            "avg_security": self.avg_security,
            "total_user_tasks": self.total_user_tasks,
            "passed_user_tasks": self.passed_user_tasks,
            "total_injection_tasks": self.total_injection_tasks,
            "passed_injection_tasks": self.passed_injection_tasks,
            "benchmark_version": self.benchmark_version,
            "utility_percent": (self.passed_user_tasks / self.total_user_tasks * 100)
            if self.total_user_tasks > 0
            else 0.0,
            "security_percent": (self.avg_security * 100),
        }


def get_all_injection_task_ids(agentdojo_dir: Path, suite: str = "workspace") -> list[str]:
    """Get all available injection task IDs for a suite by listing task classes.

    Args:
        agentdojo_dir: Path to AgentDojo repository
        suite: Suite name (default: 'workspace')

    Returns:
        List of injection task IDs (e.g., ["injection_task_0", "injection_task_1", ...])
    """
    # For the workspace suite in v1, there are injection tasks 0-5
    # We return the IDs that AgentDojo expects
    injection_task_ids = []

    # Read the injection_tasks.py file to count the number of InjectionTask classes
    if suite == "workspace":
        # Look for InjectionTask classes in the workspace suite
        injection_file = agentdojo_dir / "src" / "agentdojo" / "default_suites" / "v1" / suite / "injection_tasks.py"
        if injection_file.exists():
            with open(injection_file) as f:
                content = f.read()

            # Count InjectionTask classes (e.g., "class InjectionTask0", "class InjectionTask1", etc.)
            import re
            matches = re.findall(r'class InjectionTask(\d+)', content)
            for task_num in matches:
                injection_task_ids.append(f"injection_task_{task_num}")

    logger.info(f"Found {len(injection_task_ids)} injection tasks for suite '{suite}': {injection_task_ids}")
    return injection_task_ids


def parse_agentdojo_results(logdir: Path, suite: str = "workspace") -> Dict[str, Any]:
    """Parse AgentDojo results from the runs directory.

    Args:
        logdir: Path to AgentDojo runs directory
        suite: Suite name (default: 'workspace')

    Returns:
        Dictionary with utility_results and security_results
    """
    suite_dir = logdir / suite
    if not suite_dir.exists():
        logger.error(f"Suite directory not found: {suite_dir}")
        return {"utility_results": {}, "security_results": {}}

    utility_results = {}
    security_results = {}
    injection_tasks_utility_results = {}

    # Parse results from JSON files
    for user_task_dir in suite_dir.glob("user_task_*"):
        user_task_id = user_task_dir.name

        # Check for attack subdirectories
        for attack_dir in user_task_dir.glob("*"):
            if not attack_dir.is_dir():
                continue

            # Parse injection task results
            for injection_file in attack_dir.glob("injection_task_*.json"):
                try:
                    with open(injection_file) as f:
                        data = json.load(f)

                    injection_task_id = data.get("injection_task_id")
                    key = f"{user_task_id}_{injection_task_id}"

                    # Utility: did the agent complete the user task?
                    injection_tasks_utility_results[key] = data.get("utility", False)

                    # Security: did the agent resist the injection?
                    security_results[key] = not data.get("security", True)  # Invert: True means attack failed (secure)

                except Exception as e:
                    logger.warning(f"Failed to parse {injection_file}: {e}")

        # Parse user task results (no attack)
        user_task_file = user_task_dir / "result.json"
        if user_task_file.exists():
            try:
                with open(user_task_file) as f:
                    data = json.load(f)
                utility_results[user_task_id] = data.get("utility", False)
            except Exception as e:
                logger.warning(f"Failed to parse {user_task_file}: {e}")

    return {
        "utility_results": utility_results,
        "security_results": security_results,
        "injection_tasks_utility_results": injection_tasks_utility_results,
    }


def run_safety_benchmark(
    model_id: str,
    agentdojo_dir: Path,
    output_dir: Path,
    attack: str = "tool_knowledge",
    defense: Optional[str] = None,
    suite: str = "workspace",
    max_user_tasks: Optional[int] = 10,
    attacks_per_task: int = 1,
) -> Optional[SafetyBenchmarkResult]:
    """Run AgentDojo safety benchmark for a single model.

    Args:
        model_id: OpenRouter model ID
        agentdojo_dir: Path to AgentDojo repository
        output_dir: Path to save results
        attack: Attack type (default: 'tool_knowledge')
        defense: Defense mechanism (default: None)
        suite: Suite to run (default: 'workspace')
        max_user_tasks: Maximum number of user tasks to test (default: 10, None = all)
        attacks_per_task: Number of randomly sampled injection attacks per user task (default: 1)

    Returns:
        SafetyBenchmarkResult if successful, None otherwise
    """
    logger.info(f"Running safety benchmark for {model_id}")
    logger.info(f"  Suite: {suite}, Attack: {attack}, Defense: {defense or 'none'}")
    if max_user_tasks is not None:
        logger.info(f"  Limited to first {max_user_tasks} user tasks")
    logger.info(f"  Attacks per task: {attacks_per_task}")

    # Get all available injection tasks for random sampling
    all_injection_tasks = get_all_injection_task_ids(agentdojo_dir, suite)
    if not all_injection_tasks:
        logger.error(f"No injection tasks found for suite '{suite}'")
        return None

    # Randomly sample injection tasks (with seed for reproducibility)
    # Use model_id as seed so the same model always gets the same attacks
    rng = random.Random(hash(model_id) % (2**32))
    sampled_injection_tasks = rng.sample(
        all_injection_tasks,
        min(attacks_per_task, len(all_injection_tasks))
    )

    logger.info(f"Randomly sampled {len(sampled_injection_tasks)} injection tasks: {sampled_injection_tasks}")

    # Prepare command
    # Use absolute path for logdir so it's not relative to agentdojo cwd
    logdir_abs = (output_dir / "runs").resolve()
    cmd = [
        sys.executable,
        "-m",
        "agentdojo.scripts.benchmark",
        "--model",
        model_id,
        "--provider",
        "openrouter",
        "--suite",
        suite,
        "--attack",
        attack,
        "--logdir",
        str(logdir_abs),
    ]

    if defense:
        cmd.extend(["--defense", defense])

    # Limit to first N user tasks to speed up benchmarking
    if max_user_tasks is not None:
        for i in range(max_user_tasks):
            cmd.extend(["--user-task", f"user_task_{i}"])

    # Add randomly sampled injection tasks
    for injection_task_id in sampled_injection_tasks:
        cmd.extend(["--injection-task", injection_task_id])

    # Run benchmark
    try:
        logger.info(f"Executing: {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            cwd=agentdojo_dir,
            capture_output=True,
            text=True,
            timeout=6000,  # 100 minute timeout (safety benchmarks can be slow)
        )

        if result.returncode != 0:
            logger.error(f"AgentDojo benchmark failed for {model_id}")
            logger.error(f"  stdout: {result.stdout}")
            logger.error(f"  stderr: {result.stderr}")
            return None

        logger.info(f"AgentDojo benchmark completed for {model_id}")
        logger.debug(f"  stdout: {result.stdout}")

    except subprocess.TimeoutExpired:
        logger.error(f"AgentDojo benchmark timed out for {model_id} (100 minutes)")
        return None
    except Exception as e:
        logger.error(f"Error running AgentDojo benchmark for {model_id}: {e}")
        return None

    # Parse results
    # AgentDojo creates a directory based on the pipeline name (model ID)
    # Since we run one model at a time, just find the directory in runs/
    runs_dir = output_dir / "runs"
    if not runs_dir.exists():
        logger.error(f"Runs directory does not exist: {runs_dir}")
        return None

    # Find the model directory (should be only one since we run one model at a time)
    model_dirs = [d for d in runs_dir.iterdir() if d.is_dir()]
    if not model_dirs:
        logger.error(f"No model directories found in {runs_dir}")
        return None

    if len(model_dirs) > 1:
        logger.warning(f"Multiple model directories found in {runs_dir}: {[d.name for d in model_dirs]}")
        logger.warning(f"Using the first one: {model_dirs[0].name}")

    logdir = model_dirs[0]
    logger.info(f"Found results directory: {logdir.name}")

    results = parse_agentdojo_results(logdir, suite)

    # Calculate metrics
    utility_results = results["utility_results"]
    security_results = results["security_results"]
    injection_tasks_utility = results["injection_tasks_utility_results"]

    if not security_results:
        logger.error(f"No results found for {model_id}")
        return None

    # Group injection task utility results by user task
    # Key format is "user_task_0_injection_task_0", we want to count unique user tasks
    user_task_completion = {}
    for key, passed in injection_tasks_utility.items():
        # Extract user_task_id from key (format: "user_task_X_injection_task_Y")
        parts = key.split("_")
        if len(parts) >= 3:
            user_task_id = f"{parts[0]}_{parts[1]}_{parts[2]}"  # "user_task_X"
            if user_task_id not in user_task_completion:
                user_task_completion[user_task_id] = []
            user_task_completion[user_task_id].append(passed)

    # Utility: For each user task, did it pass ANY of the injection tests?
    # (If the task was completed despite the attack in any variant, count it as passed)
    passed_user_tasks = sum(1 for results in user_task_completion.values() if any(results))
    total_user_tasks = len(user_task_completion)
    avg_utility = (passed_user_tasks / total_user_tasks) if total_user_tasks > 0 else 0.0

    # Security: Pass@k evaluation - attack succeeds if it works in ANY of the k attempts
    # Group security results by user task to implement pass@k
    user_task_security = {}
    for key, resisted in security_results.items():
        parts = key.split("_")
        if len(parts) >= 3:
            user_task_id = f"{parts[0]}_{parts[1]}_{parts[2]}"  # "user_task_X"
            if user_task_id not in user_task_security:
                user_task_security[user_task_id] = []
            user_task_security[user_task_id].append(resisted)

    # For pass@k: attack succeeds if agent FAILS to resist in at least one attempt
    # Security score = fraction of user tasks where agent resisted ALL attacks
    tasks_with_all_attacks_resisted = sum(
        1 for results in user_task_security.values() if all(results)
    )
    total_security_tasks = len(user_task_security)
    avg_security = (
        tasks_with_all_attacks_resisted / total_security_tasks if total_security_tasks > 0 else 0.0
    )

    # Injection task stats (total 140 tests)
    passed_injection_tasks = sum(injection_tasks_utility.values())
    total_injection_tasks = len(injection_tasks_utility)

    logger.info(f"Safety benchmark results for {model_id}:")
    logger.info(f"  Utility: {avg_utility * 100:.1f}% ({passed_user_tasks}/{total_user_tasks})")
    logger.info(f"  Security: {avg_security * 100:.1f}%")
    logger.info(f"  Injection tasks passed: {passed_injection_tasks}/{total_injection_tasks}")

    return SafetyBenchmarkResult(
        model_id=model_id,
        avg_utility=avg_utility,
        avg_security=avg_security,
        total_user_tasks=total_user_tasks,
        passed_user_tasks=passed_user_tasks,
        total_injection_tasks=total_injection_tasks,
        passed_injection_tasks=passed_injection_tasks,
    )


def main():
    """Main entry point for running safety benchmarks standalone."""
    import argparse

    parser = argparse.ArgumentParser(description="Run AgentDojo safety benchmarks")
    parser.add_argument("--model", required=True, help="OpenRouter model ID")
    parser.add_argument(
        "--agentdojo-dir",
        type=Path,
        default=Path(__file__).parent.parent / "agentdojo",
        help="Path to AgentDojo repository",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/safety"),
        help="Output directory for results",
    )
    parser.add_argument(
        "--attack", default="tool_knowledge", help="Attack type (default: tool_knowledge)"
    )
    parser.add_argument("--defense", default=None, help="Defense mechanism (optional)")
    parser.add_argument("--suite", default="workspace", help="Suite to run (default: workspace)")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    result = run_safety_benchmark(
        model_id=args.model,
        agentdojo_dir=args.agentdojo_dir,
        output_dir=args.output_dir,
        attack=args.attack,
        defense=args.defense,
        suite=args.suite,
    )

    if result:
        output_file = args.output_dir / f"safety_{args.model.replace('/', '_')}.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, "w") as f:
            json.dump(result.to_dict(), f, indent=2)
        logger.info(f"Results saved to {output_file}")
    else:
        logger.error("Safety benchmark failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
