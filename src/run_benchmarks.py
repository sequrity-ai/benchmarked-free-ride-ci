#!/usr/bin/env python3
"""
Run OpenClaw benchmarks against discovered models.
Supports both utility benchmarks (openclawbench) and safety benchmarks (AgentDojo).

Uses openclawbench's run.py with --backend=daytona to run evaluations in
cloud sandboxes — no local openclaw installation required.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import argparse
import logging

# Import safety benchmark functionality
from run_safety_benchmark import run_safety_benchmark

logging.basicConfig(level=logging.INFO)


class BenchmarkRunner:
    def __init__(
        self,
        sandbox_path: Path,
        output_dir: Path,
        agentdojo_dir: Optional[Path] = None,
        run_safety: bool = False,
        provider: str = "openrouter",
        backend: str = "daytona",
    ):
        self.sandbox_path = sandbox_path
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.agentdojo_dir = agentdojo_dir
        self.run_safety = run_safety
        self.provider = provider
        self.backend = backend

        # Create separate directories for utility and safety results
        self.utility_dir = output_dir / "utility"
        self.safety_dir = output_dir / "safety"
        self.utility_dir.mkdir(parents=True, exist_ok=True)
        if run_safety:
            self.safety_dir.mkdir(parents=True, exist_ok=True)

    def _run_openclawbench(
        self,
        model_id: str,
        scenario: str,
        difficulty: str,
        output_file: Path,
    ) -> bool:
        """
        Run a single openclawbench scenario via run.py --backend daytona.

        Returns True if the benchmark completed (even if some tasks failed).
        """
        cmd = [
            "uv", "run", "python", "run.py",
            "--backend", self.backend,
            "--provider", self.provider,
            "--model", model_id,
            "--scenario", scenario,
            "--difficulty", difficulty,
            "--output", str(output_file.resolve()),
        ]

        # Forward relevant env vars (uv run inherits env automatically)
        env = os.environ.copy()

        print(f"Running command: {' '.join(cmd)}")

        try:
            result = subprocess.run(
                cmd,
                cwd=self.sandbox_path,
                env=env,
                capture_output=True,
                text=True,
                timeout=3600,  # 1 hour timeout per scenario
            )

            print(result.stdout)
            if result.stderr:
                print("STDERR:", result.stderr)

            # openclawbench exits non-zero if any task fails, but that's OK —
            # it still writes the results file. Only treat missing output as failure.
            if output_file.exists():
                return True

            print(f"Output file not found after running scenario {scenario}")
            return False

        except subprocess.TimeoutExpired:
            print(f"Scenario {scenario} timed out after 1 hour")
            return False
        except Exception as e:
            print(f"Error running scenario {scenario}: {e}")
            return False

    def run_utility_benchmark(
        self,
        model_id: str,
        scenarios: Optional[List[str]] = None,
        difficulty: str = "all",
    ) -> Optional[Dict[str, Any]]:
        """
        Run the utility benchmark for a specific model using openclawbench + Daytona.

        Runs each scenario separately via run.py and merges results.
        """
        print(f"\n{'='*60}")
        print(f"Running benchmarks for model: {model_id}")
        print(f"{'='*60}\n")

        if not scenarios:
            scenarios = ["file", "weather", "web"]

        safe_model_name = model_id.replace("/", "_").replace(":", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Run each scenario separately and collect results
        all_scenario_results = []

        for scenario in scenarios:
            print(f"\n--- Running scenario: {scenario} ---\n")

            output_file = self.utility_dir / f"utility_{safe_model_name}_{scenario}_{timestamp}.json"

            success = self._run_openclawbench(
                model_id=model_id,
                scenario=scenario,
                difficulty=difficulty,
                output_file=output_file,
            )

            if not success:
                print(f"Scenario {scenario} failed to produce output")
                continue

            try:
                with open(output_file, "r") as f:
                    scenario_result = json.load(f)

                # The new openclawbench output has task_results at top level.
                # Wrap it as a scenario entry compatible with generate_report.py.
                all_scenario_results.append({
                    "scenario_name": scenario_result.get("scenario_name", scenario),
                    "task_results": scenario_result.get("task_results", []),
                    "average_accuracy": scenario_result.get("average_accuracy", 0),
                    "average_latency": scenario_result.get("average_latency", 0),
                    "total_tokens": scenario_result.get("total_tokens", 0),
                    "total_duration": scenario_result.get("total_duration", 0),
                })

                print(f"Scenario {scenario} completed successfully!")
            except Exception as e:
                print(f"Error loading results for scenario {scenario}: {e}")
                continue

        if not all_scenario_results:
            print("No scenarios completed successfully")
            return None

        # Create merged output file (same format generate_report.py expects)
        merged_output = self.utility_dir / f"utility_{safe_model_name}_{timestamp}.json"

        total_tasks = sum(len(s.get("task_results", [])) for s in all_scenario_results)
        tasks_passed = sum(
            sum(1 for t in s.get("task_results", []) if t.get("success", False))
            for s in all_scenario_results
        )

        merged_result = {
            "scenarios": all_scenario_results,
            "summary": {
                "total_scenarios": len(all_scenario_results),
                "total_tasks": total_tasks,
                "tasks_passed": tasks_passed,
                "overall_accuracy": (tasks_passed / total_tasks * 100) if total_tasks > 0 else 0,
            },
            "model_id": model_id,
            "benchmarked_at": datetime.now().isoformat(),
        }

        with open(merged_output, "w") as f:
            json.dump(merged_result, f, indent=2)

        print(f"\nAll scenarios completed! Merged results saved to: {merged_output}")
        return merged_result

    def run_safety_benchmark_for_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        """Run the safety benchmark (AgentDojo) for a specific model."""
        if not self.run_safety:
            return None

        if not self.agentdojo_dir:
            print(f"Warning: AgentDojo directory not configured, skipping safety benchmark")
            return None

        print(f"\n{'='*60}")
        print(f"Running SAFETY benchmark for model: {model_id}")
        print(f"{'='*60}\n")

        result = run_safety_benchmark(
            model_id=model_id,
            agentdojo_dir=self.agentdojo_dir,
            output_dir=self.safety_dir,
            attack="tool_knowledge",
            defense=None,
            suite="workspace",
            max_user_tasks=10,
            attacks_per_task=5,  # Pass@5 evaluation
        )

        if result:
            safe_model_name = model_id.replace("/", "_").replace(":", "_")
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = self.safety_dir / f"safety_{safe_model_name}_{timestamp}.json"

            with open(output_file, "w") as f:
                json.dump(result.to_dict(), f, indent=2)

            print(f"Safety benchmark results saved to: {output_file}")
            return result.to_dict()

        return None

    def run_all_discovered_models(
        self,
        discovered_models_file: Path,
        scenarios: Optional[List[str]] = None,
        difficulty: str = "all",
        max_models: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Run benchmarks for all discovered models."""
        with open(discovered_models_file, "r") as f:
            data = json.load(f)
            models = data.get("models", [])

        if max_models:
            models = models[:max_models]

        print(f"Running benchmarks for {len(models)} models...")

        all_results = []

        for i, model in enumerate(models, 1):
            model_id = model["id"]
            print(f"\n[{i}/{len(models)}] Benchmarking: {model_id}")

            utility_result = self.run_utility_benchmark(
                model_id=model_id,
                scenarios=scenarios,
                difficulty=difficulty,
            )

            safety_result = None
            if self.run_safety:
                safety_result = self.run_safety_benchmark_for_model(model_id)

            if utility_result:
                utility_result["quality_score"] = model.get("quality_score", 0)
                utility_result["context_length"] = model.get("context_length", 0)
                utility_result["benchmark_type"] = "utility"

                if safety_result:
                    utility_result["safety_benchmark"] = safety_result

                all_results.append(utility_result)
            else:
                print(f"Failed to benchmark {model_id}")

        return all_results


def main():
    parser = argparse.ArgumentParser(description="Run OpenClaw benchmarks")
    parser.add_argument(
        "--discovered-models",
        type=Path,
        default=Path("output/discovered_models.json"),
        help="Path to discovered models JSON file",
    )
    parser.add_argument(
        "--sandbox-path",
        type=Path,
        default=Path("/app/openclawbench"),
        help="Path to openclawbench directory",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/benchmarks"),
        help="Output directory for benchmark results",
    )
    parser.add_argument(
        "--scenarios",
        type=str,
        default="file,weather,web",
        help="Comma-separated list of scenarios (default: file,weather,web)",
    )
    parser.add_argument(
        "--difficulty",
        type=str,
        default="easy",
        choices=["easy", "medium", "hard", "all"],
        help="Task difficulty filter (default: easy)",
    )
    parser.add_argument(
        "--max-models",
        type=int,
        default=None,
        help="Maximum number of models to benchmark",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="openrouter",
        help="LLM provider for Daytona backend (default: openrouter)",
    )
    parser.add_argument(
        "--backend",
        type=str,
        default="daytona",
        choices=["local", "daytona"],
        help="Workspace backend (default: daytona)",
    )
    parser.add_argument(
        "--run-safety",
        action="store_true",
        default=False,
        help="Run safety benchmarks (AgentDojo) in addition to utility benchmarks",
    )
    parser.add_argument(
        "--agentdojo-dir",
        type=Path,
        default=None,
        help="Path to AgentDojo repository (required if --run-safety is enabled)",
    )

    args = parser.parse_args()

    # Validate safety benchmark configuration
    if args.run_safety and not args.agentdojo_dir:
        args.agentdojo_dir = Path(__file__).parent.parent / "agentdojo"
        if not args.agentdojo_dir.exists():
            print(f"Error: --run-safety requires --agentdojo-dir or agentdojo submodule")
            sys.exit(1)

    # Validate sandbox path
    if not args.sandbox_path.exists():
        print(f"Error: Sandbox path not found: {args.sandbox_path}")
        sys.exit(1)

    # Validate discovered models file
    if not args.discovered_models.exists():
        print(f"Error: Discovered models file not found: {args.discovered_models}")
        print("Run discover_models.py first!")
        sys.exit(1)

    runner = BenchmarkRunner(
        sandbox_path=args.sandbox_path,
        output_dir=args.output_dir,
        agentdojo_dir=args.agentdojo_dir,
        run_safety=args.run_safety,
        provider=args.provider,
        backend=args.backend,
    )

    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]

    results = runner.run_all_discovered_models(
        discovered_models_file=args.discovered_models,
        scenarios=scenarios,
        difficulty=args.difficulty,
        max_models=args.max_models,
    )

    print(f"\n{'='*60}")
    print(f"Benchmark Summary")
    print(f"{'='*60}")
    print(f"Total models benchmarked: {len(results)}")
    print(f"Results saved to: {args.output_dir}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
