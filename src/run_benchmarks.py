#!/usr/bin/env python3
"""
Run OpenClaw benchmarks against discovered models.
Supports both utility benchmarks (openclaw-sandbox) and safety benchmarks (AgentDojo).
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
        run_safety: bool = False
    ):
        self.sandbox_path = sandbox_path
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.agentdojo_dir = agentdojo_dir
        self.run_safety = run_safety

        # Create separate directories for utility and safety results
        self.utility_dir = output_dir / "utility"
        self.safety_dir = output_dir / "safety"
        self.utility_dir.mkdir(parents=True, exist_ok=True)
        if run_safety:
            self.safety_dir.mkdir(parents=True, exist_ok=True)

    def configure_openclaw_model(self, model_id: str) -> bool:
        """Configure OpenClaw to use the specified model."""
        try:
            # Use openclaw models set command
            result = subprocess.run(
                ["openclaw", "models", "set", f"openrouter/{model_id}"],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                print(f"Warning: Failed to set model via CLI: {result.stderr}")
                return False

            print(f"Configured OpenClaw to use model: openrouter/{model_id}")
            return True

        except Exception as e:
            print(f"Error configuring model {model_id}: {e}")
            return False

    def run_utility_benchmark(
        self,
        model_id: str,
        scenarios: Optional[List[str]] = None,
        single_turn: bool = True,
        difficulty: str = "all"
    ) -> Optional[Dict[str, Any]]:
        """
        Run the utility benchmark (openclaw-sandbox) for a specific model.

        Args:
            model_id: The OpenRouter model ID
            scenarios: List of scenarios to run (runs each individually and merges results)
            single_turn: Use single-turn mode (faster, no OpenAI API needed)
            difficulty: Task difficulty filter (easy/medium/hard/all)

        Returns:
            Benchmark results as dict, or None if failed
        """
        print(f"\n{'='*60}")
        print(f"Running benchmarks for model: {model_id}")
        print(f"{'='*60}\n")

        # Configure OpenClaw to use this model
        if not self.configure_openclaw_model(model_id):
            print(f"Skipping benchmarks for {model_id} due to configuration error")
            return None

        # Default scenarios if none specified
        if not scenarios:
            scenarios = ["file", "weather", "web"]

        # Prepare output filename
        safe_model_name = model_id.replace("/", "_").replace(":", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Run each scenario separately and collect results
        all_scenario_results = []

        for scenario in scenarios:
            print(f"\n--- Running scenario: {scenario} ---\n")

            output_file = self.utility_dir / f"utility_{safe_model_name}_{scenario}_{timestamp}.json"
            output_file_abs = output_file.resolve()
            output_file_abs.parent.mkdir(parents=True, exist_ok=True)

            # Build command for single scenario
            cmd = [
                "python3",
                "cli.py",
                "--local",
                "benchmark-suite",
                "--scenario", scenario,
                "--difficulty", difficulty,
                "-o", str(output_file_abs)
            ]

            if single_turn:
                cmd.append("--single-turn")

            # Set environment variables
            env = os.environ.copy()
            env["LOCAL_MODE"] = "true"
            env["AGENT_ID"] = "main"

            print(f"Running command: {' '.join(cmd)}\n")

            try:
                # Run benchmark
                result = subprocess.run(
                    cmd,
                    cwd=self.sandbox_path,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=3600  # 1 hour timeout
                )

                print(result.stdout)

                if result.stderr:
                    print("STDERR:", result.stderr)

                if result.returncode != 0:
                    print(f"Scenario {scenario} failed with return code {result.returncode}")
                    continue

                # Load scenario results
                if output_file.exists():
                    with open(output_file, "r") as f:
                        scenario_result = json.load(f)

                    # Extract the scenarios list from the result
                    if "scenarios" in scenario_result:
                        all_scenario_results.extend(scenario_result["scenarios"])

                    print(f"Scenario {scenario} completed successfully!")
                else:
                    print(f"Output file not found for scenario {scenario}: {output_file}")

            except subprocess.TimeoutExpired:
                print(f"Scenario {scenario} timed out after 1 hour")
                continue
            except Exception as e:
                print(f"Error running scenario {scenario}: {e}")
                continue

        # Merge all results into a single output
        if not all_scenario_results:
            print("No scenarios completed successfully")
            return None

        # Create merged output file
        merged_output = self.utility_dir / f"utility_{safe_model_name}_{timestamp}.json"

        # Calculate merged summary
        total_tasks = sum(len(s.get("task_results", [])) for s in all_scenario_results)
        tasks_passed = sum(
            sum(1 for t in s.get("task_results", []) if t.get("success", False))
            for s in all_scenario_results
        )

        merged_result = {
            "config": {
                "async_mode": False,
                "local_mode": True,
                "bot_model": None,
                "mode": "single_turn"
            },
            "scenarios": all_scenario_results,
            "summary": {
                "total_scenarios": len(all_scenario_results),
                "total_tasks": total_tasks,
                "tasks_passed": tasks_passed,
                "overall_accuracy": (tasks_passed / total_tasks * 100) if total_tasks > 0 else 0
            },
            "model_id": model_id,
            "benchmarked_at": datetime.now().isoformat()
        }

        # Save merged result
        with open(merged_output, "w") as f:
            json.dump(merged_result, f, indent=2)

        print(f"\nAll scenarios completed! Merged results saved to: {merged_output}")
        return merged_result

    def run_safety_benchmark_for_model(self, model_id: str) -> Optional[Dict[str, Any]]:
        """
        Run the safety benchmark (AgentDojo) for a specific model.

        Args:
            model_id: The OpenRouter model ID

        Returns:
            Safety benchmark results as dict, or None if failed or not supported
        """
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
            suite="workspace"
        )

        if result:
            # Save result to file
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
        single_turn: bool = True,
        difficulty: str = "all",
        max_models: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Run benchmarks for all discovered models.

        Args:
            discovered_models_file: Path to discovered_models.json
            scenarios: List of scenarios to run
            single_turn: Use single-turn mode
            difficulty: Task difficulty filter
            max_models: Maximum number of models to benchmark (None = all)

        Returns:
            List of benchmark results
        """
        # Load discovered models
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

            # Run utility benchmark
            utility_result = self.run_utility_benchmark(
                model_id=model_id,
                scenarios=scenarios,
                single_turn=single_turn,
                difficulty=difficulty
            )

            # Run safety benchmark (if enabled)
            safety_result = None
            if self.run_safety:
                safety_result = self.run_safety_benchmark_for_model(model_id)

            if utility_result:
                # Add model metadata from discovery
                utility_result["quality_score"] = model.get("quality_score", 0)
                utility_result["context_length"] = model.get("context_length", 0)
                utility_result["benchmark_type"] = "utility"

                # Add safety results if available
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
        help="Path to discovered models JSON file"
    )
    parser.add_argument(
        "--sandbox-path",
        type=Path,
        default=Path("/app/openclaw-benchmark"),
        help="Path to openclaw-benchmark directory"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/benchmarks"),
        help="Output directory for benchmark results"
    )
    parser.add_argument(
        "--scenarios",
        type=str,
        default="file,weather,web",
        help="Comma-separated list of scenarios (default: file,weather,web)"
    )
    parser.add_argument(
        "--single-turn",
        action="store_true",
        default=True,
        help="Use single-turn mode (no AI agent)"
    )
    parser.add_argument(
        "--difficulty",
        type=str,
        default="easy",
        choices=["easy", "medium", "hard", "all"],
        help="Task difficulty filter (default: easy)"
    )
    parser.add_argument(
        "--max-models",
        type=int,
        default=None,
        help="Maximum number of models to benchmark"
    )
    parser.add_argument(
        "--run-safety",
        action="store_true",
        default=False,
        help="Run safety benchmarks (AgentDojo) in addition to utility benchmarks"
    )
    parser.add_argument(
        "--agentdojo-dir",
        type=Path,
        default=None,
        help="Path to AgentDojo repository (required if --run-safety is enabled)"
    )

    args = parser.parse_args()

    # Validate safety benchmark configuration
    if args.run_safety and not args.agentdojo_dir:
        # Default to sibling directory
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

    # Create runner
    runner = BenchmarkRunner(
        sandbox_path=args.sandbox_path,
        output_dir=args.output_dir,
        agentdojo_dir=args.agentdojo_dir,
        run_safety=args.run_safety
    )

    # Parse scenarios
    scenarios = [s.strip() for s in args.scenarios.split(",") if s.strip()]

    # Run benchmarks
    results = runner.run_all_discovered_models(
        discovered_models_file=args.discovered_models,
        scenarios=scenarios,
        single_turn=args.single_turn,
        difficulty=args.difficulty,
        max_models=args.max_models
    )

    print(f"\n{'='*60}")
    print(f"Benchmark Summary")
    print(f"{'='*60}")
    print(f"Total models benchmarked: {len(results)}")
    print(f"Results saved to: {args.output_dir}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
