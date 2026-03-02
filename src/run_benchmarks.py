#!/usr/bin/env python3
"""
Run OpenClaw benchmarks against discovered models.
Integrates with the openclaw-sandbox benchmark suite.
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import argparse


class BenchmarkRunner:
    def __init__(self, sandbox_path: Path, output_dir: Path):
        self.sandbox_path = sandbox_path
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def configure_openclaw_model(self, model_id: str) -> bool:
        """Configure OpenClaw to use the specified model."""
        try:
            # Use openclaw CLI to set the model
            result = subprocess.run(
                ["openclaw", "config", "set", "model", model_id],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                print(f"Warning: Failed to set model via CLI: {result.stderr}")
                # Try alternative: directly modify config file
                return self._configure_model_via_config(model_id)

            print(f"Configured OpenClaw to use model: {model_id}")
            return True

        except Exception as e:
            print(f"Error configuring model {model_id}: {e}")
            return False

    def _configure_model_via_config(self, model_id: str) -> bool:
        """Fallback: Directly modify OpenClaw config file."""
        try:
            config_path = Path.home() / ".openclaw" / "config.json"

            if not config_path.exists():
                print(f"Config file not found at {config_path}")
                return False

            with open(config_path, "r") as f:
                config = json.load(f)

            # Set the model
            if "agents" not in config:
                config["agents"] = {}
            if "defaults" not in config["agents"]:
                config["agents"]["defaults"] = {}
            if "model" not in config["agents"]["defaults"]:
                config["agents"]["defaults"]["model"] = {}

            config["agents"]["defaults"]["model"]["primary"] = f"openrouter/{model_id}"

            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)

            print(f"Configured model via config file: {model_id}")
            return True

        except Exception as e:
            print(f"Error modifying config file: {e}")
            return False

    def run_benchmark_suite(
        self,
        model_id: str,
        scenarios: Optional[List[str]] = None,
        single_turn: bool = True,
        difficulty: str = "all"
    ) -> Optional[Dict[str, Any]]:
        """
        Run the openclaw-sandbox benchmark suite for a specific model.

        Args:
            model_id: The OpenRouter model ID
            scenarios: List of scenarios to run (default: all)
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

        # Prepare output filename
        safe_model_name = model_id.replace("/", "_").replace(":", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = self.output_dir / f"benchmark_{safe_model_name}_{timestamp}.json"

        # Build command
        cmd = [
            "python3",
            str(self.sandbox_path / "cli.py"),
            "--local",
            "benchmark-suite",
            "--scenario", ",".join(scenarios) if scenarios else "all",
            "--difficulty", difficulty,
            "-o", str(output_file)
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
                print(f"Benchmark failed with return code {result.returncode}")
                return None

            # Load and return results
            if output_file.exists():
                with open(output_file, "r") as f:
                    results = json.load(f)

                # Add model metadata
                results["model_id"] = model_id
                results["benchmarked_at"] = datetime.now().isoformat()

                print(f"\nBenchmark completed successfully!")
                print(f"Results saved to: {output_file}")

                return results
            else:
                print(f"Output file not found: {output_file}")
                return None

        except subprocess.TimeoutExpired:
            print(f"Benchmark timed out after 1 hour")
            return None
        except Exception as e:
            print(f"Error running benchmark: {e}")
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

            result = self.run_benchmark_suite(
                model_id=model_id,
                scenarios=scenarios,
                single_turn=single_turn,
                difficulty=difficulty
            )

            if result:
                # Add model metadata from discovery
                result["quality_score"] = model.get("quality_score", 0)
                result["context_length"] = model.get("context_length", 0)
                all_results.append(result)
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

    args = parser.parse_args()

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
        output_dir=args.output_dir
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
