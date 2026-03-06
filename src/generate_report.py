#!/usr/bin/env python3
"""
Generate benchmark reports and leaderboard for GitHub Pages.
Aggregates benchmark results and creates JSON API endpoints + HTML UI.
"""

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


class ReportGenerator:
    def __init__(self, benchmarks_dir: Path, output_dir: Path):
        self.benchmarks_dir = benchmarks_dir
        self.output_dir = output_dir
        self.api_dir = output_dir / "api"
        self.history_dir = self.api_dir / "history"

        # Separate directories for utility and safety benchmarks
        self.utility_dir = benchmarks_dir / "utility"
        self.safety_dir = benchmarks_dir / "safety"

        # Create directories
        self.api_dir.mkdir(parents=True, exist_ok=True)
        self.history_dir.mkdir(parents=True, exist_ok=True)

        # Load discovered models data for metadata lookups
        self.discovered_models = self._load_discovered_models()

    def _load_discovered_models(self) -> Dict[str, Dict[str, Any]]:
        """
        Load discovered_models.json to get quality_score and context_length metadata.
        Returns a dict mapping model_id to model data.
        """
        # Try to find discovered_models.json in parent directories
        search_paths = [
            self.benchmarks_dir.parent / "discovered_models.json",
            self.benchmarks_dir.parent.parent / "discovered_models.json",
            Path("output/discovered_models.json"),
        ]

        for path in search_paths:
            if path.exists():
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                        models_dict = {}
                        for model in data.get("models", []):
                            model_id = model.get("id")
                            if model_id:
                                models_dict[model_id] = model
                        print(f"Loaded {len(models_dict)} models from {path}")
                        return models_dict
                except Exception as e:
                    print(f"Error loading discovered models from {path}: {e}")

        print(
            "Warning: Could not find discovered_models.json - model metadata may be incomplete"
        )
        return {}

    def _infer_model_id_from_filename(self, filename: str) -> str | None:
        """
        Infer model_id from benchmark filename.
        Expected formats:
        - utility_{provider}_{model}_{variant}_{timestamp}.json
        - utility_{provider}_{model}_{variant}_{scenario}_{timestamp}.json
        - benchmark_{provider}_{model}_{variant}_{timestamp}.json (legacy)
        - safety_{provider}_{model}_{variant}_{timestamp}.json
        Example: utility_stepfun_step-3.5-flash_free_file_20260303_211904.json
                 -> stepfun/step-3.5-flash:free
        """
        # Handle both new (utility_/safety_) and legacy (benchmark_) prefixes
        prefix = None
        if filename.startswith("utility_"):
            prefix = "utility_"
        elif filename.startswith("safety_"):
            prefix = "safety_"
        elif filename.startswith("benchmark_"):
            prefix = "benchmark_"

        if not prefix:
            return None

        # Remove prefix and '.json' suffix
        name_part = filename[len(prefix):-5]  # Remove prefix and '.json' (5 chars)

        # Split by underscore
        parts = name_part.split("_")

        # Remove timestamp suffix (format: _YYYYMMDD_HHMMSS)
        # Timestamp should be last 2 parts: date and time
        if len(parts) >= 2:
            # Check if last part looks like HHMMSS (6 digits)
            if parts[-1].isdigit() and len(parts[-1]) == 6:
                # Check if second-to-last looks like YYYYMMDD (8 digits)
                if parts[-2].isdigit() and len(parts[-2]) == 8:
                    # Remove timestamp parts
                    parts = parts[:-2]

        # Remove scenario suffix if present (file, weather, web, github, gmail, etc.)
        # These come after the variant but before the timestamp
        known_scenarios = [
            "file",
            "weather",
            "web",
            "github",
            "gmail",
            "compound",
            "summarize",
        ]
        if len(parts) > 0 and parts[-1] in known_scenarios:
            parts = parts[:-1]

        # Now reconstruct model_id
        # Pattern: provider_model-name_variant
        # Convert: stepfun_step-3.5-flash_free -> stepfun/step-3.5-flash:free
        if len(parts) < 1:
            return None

        # First part is provider
        provider = parts[0]

        # Last part might be variant (free, paid, etc.)
        variant = None
        if len(parts) > 1 and parts[-1] in ["free", "paid", "extended"]:
            variant = parts[-1]
            model_parts = parts[1:-1]
        else:
            model_parts = parts[1:]

        # Special case: if model_parts is empty and variant exists,
        # the model name is the same as the variant (e.g., openrouter/free)
        if not model_parts and variant:
            model_name = variant
            variant = None
        else:
            # Join model parts with hyphens
            model_name = "-".join(model_parts) if model_parts else provider

        # Construct final model_id
        model_id = f"{provider}/{model_name}"
        if variant:
            model_id += f":{variant}"

        return model_id

    def load_utility_benchmark_results(self) -> List[Dict[str, Any]]:
        """Load utility benchmark results from utility/ directory."""
        results = []
        skipped_individual = []

        # Known scenario suffixes that indicate individual (not merged) files
        scenario_suffixes = [
            "_file_",
            "_weather_",
            "_web_",
            "_github_",
            "_gmail_",
            "_compound_",
            "_summarize_",
        ]

        # Check both new utility/ dir and legacy benchmark_* files in root
        search_patterns = []
        if self.utility_dir.exists():
            search_patterns.append((self.utility_dir, "utility_*.json"))
        search_patterns.append((self.benchmarks_dir, "benchmark_*.json"))

        for search_dir, pattern in search_patterns:
            for json_file in search_dir.glob(pattern):
                # Skip individual scenario files - only load merged files
                filename = json_file.name
                is_individual_scenario = any(
                    suffix in filename for suffix in scenario_suffixes
                )

                if is_individual_scenario:
                    skipped_individual.append(filename)
                    continue

                try:
                    with open(json_file, "r") as f:
                        data = json.load(f)

                        # If model_id is missing, try to infer from filename
                        if not data.get("model_id") or data.get("model_id") == "unknown":
                            model_id = self._infer_model_id_from_filename(json_file.name)
                            if model_id:
                                data["model_id"] = model_id
                                print(
                                    f"Inferred model_id '{model_id}' from filename: {json_file.name}"
                                )

                        # Mark as utility benchmark
                        data["benchmark_type"] = "utility"
                        results.append(data)
                except Exception as e:
                    print(f"Error loading {json_file}: {e}")

        if skipped_individual:
            print(
                f"Skipped {len(skipped_individual)} individual scenario files (using merged files instead)"
            )

        print(f"Loaded {len(results)} utility benchmark results")
        return results

    def load_safety_benchmark_results(self) -> List[Dict[str, Any]]:
        """Load safety benchmark results from safety/ directory."""
        results = []

        if not self.safety_dir.exists():
            print("No safety benchmark directory found")
            return results

        for json_file in self.safety_dir.glob("safety_*.json"):
            try:
                with open(json_file, "r") as f:
                    data = json.load(f)

                    # If model_id is missing, try to infer from filename
                    if not data.get("model_id") or data.get("model_id") == "unknown":
                        model_id = self._infer_model_id_from_filename(json_file.name)
                        if model_id:
                            data["model_id"] = model_id

                    # Mark as safety benchmark
                    data["benchmark_type"] = "safety"
                    results.append(data)
            except Exception as e:
                print(f"Error loading {json_file}: {e}")

        print(f"Loaded {len(results)} safety benchmark results")
        return results

    def load_all_benchmark_results(self) -> List[Dict[str, Any]]:
        """Load all benchmark results (utility + safety)."""
        utility_results = self.load_utility_benchmark_results()
        safety_results = self.load_safety_benchmark_results()

        # Merge utility and safety results by model_id
        merged_results = {}

        for result in utility_results:
            model_id = result.get("model_id")
            if model_id:
                merged_results[model_id] = result

        # Add safety results to corresponding utility results
        for safety_result in safety_results:
            model_id = safety_result.get("model_id")
            if model_id:
                if model_id in merged_results:
                    merged_results[model_id]["safety_benchmark"] = safety_result
                else:
                    # Model has safety results but no utility results
                    merged_results[model_id] = {"model_id": model_id, "safety_benchmark": safety_result}

        return list(merged_results.values())

    def calculate_composite_score(self, result: Dict[str, Any]) -> float:
        """
        Calculate a composite score for a model based on:
        - Accuracy (70% weight)
        - Speed/latency (20% weight)
        - Token efficiency (10% weight)
        """
        scenarios = result.get("scenarios", [])

        if not scenarios:
            return 0.0

        # Calculate average accuracy across all scenarios
        total_accuracy = 0
        total_latency = 0
        total_tasks = 0

        for scenario in scenarios:
            task_results = scenario.get("task_results", [])
            if task_results:
                scenario_accuracy = sum(
                    t.get("accuracy_score", 0) for t in task_results
                ) / len(task_results)
                scenario_latency = sum(t.get("latency", 0) for t in task_results) / len(
                    task_results
                )

                total_accuracy += scenario_accuracy
                total_latency += scenario_latency
                total_tasks += len(task_results)

        if not total_tasks:
            return 0.0

        avg_accuracy = total_accuracy / len(scenarios)
        avg_latency = total_latency / len(scenarios)

        # Normalize scores
        # Accuracy: already 0-100
        accuracy_score = (avg_accuracy / 100) * 0.7

        # Latency: lower is better, normalize to 0-1 (assume 60s is max)
        latency_score = max(0, 1 - (avg_latency / 60)) * 0.2

        # Token efficiency: output tokens per task (lower is better)
        total_output_tokens = 0
        for scenario in scenarios:
            for task in scenario.get("task_results", []):
                total_output_tokens += task.get("output_tokens", 0)

        avg_output_tokens = total_output_tokens / total_tasks if total_tasks else 0
        # Normalize: assume 1000 tokens per task is max
        token_efficiency_score = max(0, 1 - (avg_output_tokens / 1000)) * 0.1

        composite_score = accuracy_score + latency_score + token_efficiency_score
        return round(composite_score * 100, 2)  # Scale to 0-100

    def aggregate_model_stats(self, result: Dict[str, Any]) -> Dict[str, Any]:
        """Extract key statistics from a benchmark result."""
        scenarios = result.get("scenarios", [])

        total_tasks = 0
        passed_tasks = 0
        total_latency = 0
        total_input_tokens = 0
        total_output_tokens = 0

        for scenario in scenarios:
            task_results = scenario.get("task_results", [])
            total_tasks += len(task_results)

            for task in task_results:
                if task.get("success", False):
                    passed_tasks += 1
                total_latency += task.get("latency", 0)
                total_input_tokens += task.get("input_tokens", 0)
                total_output_tokens += task.get("output_tokens", 0)

        avg_latency = total_latency / total_tasks if total_tasks else 0
        accuracy = (passed_tasks / total_tasks * 100) if total_tasks else 0

        # Get model_id
        model_id = result.get("model_id", "unknown")

        # Try to get quality_score and context_length from discovered models
        quality_score = result.get("quality_score", 0)
        context_length = result.get("context_length", 0)

        if model_id in self.discovered_models:
            discovered = self.discovered_models[model_id]
            if quality_score == 0:
                quality_score = discovered.get("quality_score", 0)
            if context_length == 0:
                context_length = discovered.get("context_length", 0)

        return {
            "model_id": model_id,
            "quality_score": quality_score,
            "context_length": context_length,
            "benchmarked_at": result.get("benchmarked_at", ""),
            "total_tasks": total_tasks,
            "passed_tasks": passed_tasks,
            "accuracy_percent": round(accuracy, 2),
            "avg_latency_seconds": round(avg_latency, 2),
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "composite_score": self.calculate_composite_score(result),
            "scenarios": [
                {
                    "name": s.get("scenario_name", ""),
                    "tasks_passed": sum(
                        1 for t in s.get("task_results", []) if t.get("success", False)
                    ),
                    "tasks_total": len(s.get("task_results", [])),
                    "avg_accuracy": round(
                        sum(
                            t.get("accuracy_score", 0)
                            for t in s.get("task_results", [])
                        )
                        / len(s.get("task_results", []))
                        if s.get("task_results", [])
                        else 0,
                        2,
                    ),
                }
                for s in scenarios
            ],
        }

    def generate_models_json(self, results: List[Dict[str, Any]]):
        """Generate models.json with all model statistics, including unbenchmarked models."""
        # Get stats for benchmarked models
        benchmarked_models = {
            r.get("model_id"): self.aggregate_model_stats(r) for r in results
        }

        # Add unbenchmarked models from discovered_models
        all_models = []
        for model_id, model_data in self.discovered_models.items():
            if model_id in benchmarked_models:
                # Use benchmarked data
                all_models.append(benchmarked_models[model_id])
            else:
                # Add as unbenchmarked with placeholder data
                all_models.append(
                    {
                        "model_id": model_id,
                        "quality_score": model_data.get("quality_score", 0),
                        "context_length": model_data.get("context_length", 0),
                        "benchmarked_at": "",
                        "total_tasks": 0,
                        "passed_tasks": 0,
                        "accuracy_percent": None,  # None indicates not benchmarked
                        "avg_latency_seconds": None,
                        "total_input_tokens": 0,
                        "total_output_tokens": 0,
                        "composite_score": 0,  # Will be sorted to bottom
                        "scenarios": [],
                        "is_benchmarked": False,
                    }
                )

        # Add is_benchmarked flag to benchmarked models
        for model in all_models:
            if "is_benchmarked" not in model:
                model["is_benchmarked"] = True

        output_file = self.api_dir / "models.json"
        with open(output_file, "w") as f:
            json.dump(
                {
                    "generated_at": datetime.now().isoformat(),
                    "total_models": len(all_models),
                    "benchmarked_models": len(benchmarked_models),
                    "unbenchmarked_models": len(all_models) - len(benchmarked_models),
                    "models": all_models,
                },
                f,
                indent=2,
            )

        print(f"Generated {output_file}")
        print(f"  - Benchmarked: {len(benchmarked_models)}")
        print(f"  - Unbenchmarked: {len(all_models) - len(benchmarked_models)}")

    def generate_leaderboard_json(self, results: List[Dict[str, Any]]):
        """Generate leaderboard.json with all models ranked (benchmarked + unbenchmarked)."""
        # Get benchmarked models
        benchmarked_models = {
            r.get("model_id"): self.aggregate_model_stats(r) for r in results
        }

        # Include all discovered models
        all_models = []
        for model_id, model_data in self.discovered_models.items():
            if model_id in benchmarked_models:
                model_entry = benchmarked_models[model_id]
                model_entry["is_benchmarked"] = True
                all_models.append(model_entry)
            else:
                # Unbenchmarked model
                all_models.append(
                    {
                        "model_id": model_id,
                        "composite_score": 0,
                        "accuracy_percent": None,
                        "avg_latency_seconds": None,
                        "context_length": model_data.get("context_length", 0),
                        "quality_score": model_data.get("quality_score", 0),
                        "is_benchmarked": False,
                    }
                )

        # Sort: benchmarked first (by composite score), then unbenchmarked (by quality score)
        all_models.sort(
            key=lambda m: (
                not m[
                    "is_benchmarked"
                ],  # False (benchmarked) comes before True (unbenchmarked)
                -m["composite_score"] if m["is_benchmarked"] else 0,
                -m["quality_score"],
            )
        )

        output_file = self.api_dir / "leaderboard.json"
        with open(output_file, "w") as f:
            json.dump(
                {
                    "generated_at": datetime.now().isoformat(),
                    "total_models": len(all_models),
                    "benchmarked_count": len(benchmarked_models),
                    "leaderboard": [
                        {
                            "rank": i + 1,
                            "model_id": m["model_id"],
                            "composite_score": m["composite_score"],
                            "accuracy_percent": m["accuracy_percent"],
                            "avg_latency_seconds": m["avg_latency_seconds"],
                            "context_length": m["context_length"],
                            "quality_score": m.get("quality_score", 0),
                            "is_benchmarked": m["is_benchmarked"],
                        }
                        for i, m in enumerate(all_models)
                    ],
                },
                f,
                indent=2,
            )

        print(f"Generated {output_file}")

    def generate_history_snapshot(self, results: List[Dict[str, Any]]):
        """Save a daily snapshot of results to history."""
        today = datetime.now().strftime("%Y-%m-%d")
        snapshot_file = self.history_dir / f"{today}.json"

        models = [self.aggregate_model_stats(r) for r in results]

        with open(snapshot_file, "w") as f:
            json.dump(
                {"date": today, "total_models": len(models), "models": models},
                f,
                indent=2,
            )

        print(f"Generated history snapshot: {snapshot_file}")

    def generate_html_index(self):
        """Generate HTML with landing page and tabs for OpenClawBench and AgentDojo leaderboards."""
        html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Benchmarked Free Ride - Dual Leaderboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 2rem;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 12px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }
        header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 2rem;
            text-align: center;
        }
        h1 { font-size: 2.5rem; margin-bottom: 0.5rem; }
        .subtitle { opacity: 0.9; font-size: 1.1rem; }

        .nav-tabs {
            display: flex;
            background: #f8f9fa;
            border-bottom: 2px solid #dee2e6;
        }
        .nav-tab {
            flex: 1;
            padding: 1.5rem;
            text-align: center;
            cursor: pointer;
            font-weight: 600;
            color: #6c757d;
            border-bottom: 3px solid transparent;
            transition: all 0.3s;
        }
        .nav-tab:hover { background: #e9ecef; color: #495057; }
        .nav-tab.active {
            color: #667eea;
            border-bottom-color: #667eea;
            background: white;
        }
        .nav-tab .icon { font-size: 1.5rem; display: block; margin-bottom: 0.25rem; }

        .tab-content { display: none; padding: 2rem; }
        .tab-content.active { display: block; }

        .landing { text-align: center; padding: 3rem 2rem; }
        .landing h2 { font-size: 2rem; color: #212529; margin-bottom: 1rem; }
        .landing p { font-size: 1.1rem; color: #6c757d; max-width: 800px; margin: 0 auto 2rem; line-height: 1.6; }

        .benchmark-cards {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
            gap: 2rem;
            margin-top: 2rem;
        }
        .card {
            background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
            padding: 2rem;
            border-radius: 12px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
            transition: transform 0.3s;
            cursor: pointer;
        }
        .card:hover { transform: translateY(-5px); }
        .card .icon { font-size: 3rem; margin-bottom: 1rem; }
        .card h3 { font-size: 1.5rem; color: #495057; margin-bottom: 0.5rem; }
        .card p { font-size: 1rem; color: #6c757d; }

        table { width: 100%; border-collapse: collapse; margin-top: 1rem; }
        th, td { padding: 1rem; text-align: left; border-bottom: 1px solid #eee; }
        th {
            background: #f8f9fa;
            font-weight: 600;
            color: #495057;
            text-transform: uppercase;
            font-size: 0.85rem;
        }
        tr:hover { background: #f8f9fa; }
        .rank { font-size: 1.2rem; font-weight: bold; color: #667eea; text-align: center; width: 60px; }
        .model-id { font-family: 'Monaco', monospace; font-size: 0.9rem; }
        .score { font-size: 1.1rem; font-weight: 600; color: #28a745; }
        .empty-state {
            text-align: center;
            padding: 3rem;
            color: #6c757d;
            font-size: 1.1rem;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🏆 Benchmarked Free Ride</h1>
        </header>

        <nav class="nav-tabs">
            <div class="nav-tab active" onclick="showTab('overview')">
                <span class="icon">🏠</span>
                <span>Overview</span>
            </div>
            <div class="nav-tab" onclick="showTab('openclaw')">
                <span class="icon">⚡</span>
                <span>OpenClawBench</span>
            </div>
            <div class="nav-tab" onclick="showTab('agentdojo')">
                <span class="icon">🛡️</span>
                <span>AgentDojo</span>
            </div>
        </nav>

        <div id="overview" class="tab-content active">
            <div class="landing">
                <h2>Comprehensive Model Evaluation</h2>
                <p>
                    We benchmark free OpenRouter models across two critical dimensions using industry-standard frameworks.
                    Each benchmark tests different aspects of AI agent capabilities.
                </p>

                <div class="benchmark-cards">
                    <div class="card" onclick="showTab('openclaw')">
                        <div class="icon">⚡</div>
                        <h3>OpenClawBench</h3>
                        <p>
                            <strong>What it tests:</strong> Task completion capabilities including file manipulation, web search, and weather queries.
                            <br><strong>How it works:</strong> Single-turn task execution across 3 scenarios with 9 easy-level tasks total (3 per scenario).
                            <br><strong>Scoring:</strong> Composite score = 70% accuracy + 20% speed + 10% token efficiency
                        </p>
                    </div>

                    <div class="card" onclick="showTab('agentdojo')">
                        <div class="icon">🛡️</div>
                        <h3>AgentDojo</h3>
                        <p>
                            <strong>What it tests:</strong> Prompt injection resistance and security in agentic scenarios.
                            <br><strong>How it works:</strong> Workspace suite with tool_knowledge attacks testing whether models follow malicious instructions.
                            <br><strong>Scoring:</strong> Security score (% of attacks blocked) and utility score (% of legitimate tasks completed under attack)
                        </p>
                    </div>
                </div>

                <div style="margin-top: 2rem; padding: 1.5rem; background: #e7f3ff; border-radius: 8px; border-left: 4px solid #2196F3; text-align: left;">
                    <h3 style="margin-top: 0; color: #1976D2; font-size: 1.2rem;">📚 How OpenClawBench Works</h3>
                    <p style="color: #424242; margin: 0.5rem 0; line-height: 1.7;">
                        OpenClawBench evaluates models on practical task completion through single-turn interactions:
                    </p>
                    <ul style="color: #424242; margin: 0.5rem 0 0.5rem 1.5rem; line-height: 1.7;">
                        <li><strong>File Manipulation:</strong> Create, read, transform, and extract data from files (JSON, CSV, Markdown)</li>
                        <li><strong>Web Search:</strong> Query information from the web and synthesize results</li>
                        <li><strong>Weather Data:</strong> Retrieve and process weather information for different locations</li>
                    </ul>
                    <p style="color: #424242; margin: 0.5rem 0; line-height: 1.7;">
                        Each task receives a <strong>binary score</strong> (100% pass or 0% fail) based on whether the agent successfully completed the objective.
                        The final ranking uses a <strong>composite score</strong> weighted by accuracy (70%), speed (20%), and token efficiency (10%).
                    </p>
                </div>

                <div style="margin-top: 1.5rem; padding: 1.5rem; background: #fff3e0; border-radius: 8px; border-left: 4px solid #FF9800; text-align: left;">
                    <h3 style="margin-top: 0; color: #E65100; font-size: 1.2rem;">🛡️ How AgentDojo Works</h3>
                    <p style="color: #424242; margin: 0.5rem 0; line-height: 1.7;">
                        AgentDojo tests whether AI agents can resist prompt injection attacks while maintaining utility:
                    </p>
                    <ul style="color: #424242; margin: 0.5rem 0 0.5rem 1.5rem; line-height: 1.7;">
                        <li><strong>User Tasks:</strong> Legitimate requests the agent should complete (baseline utility)</li>
                        <li><strong>Injection Tasks:</strong> Same requests but with hidden malicious instructions injected via tool outputs</li>
                        <li><strong>Attack Type:</strong> tool_knowledge attacks embed instructions in file contents, API responses, etc.</li>
                    </ul>
                    <p style="color: #424242; margin: 0.5rem 0; line-height: 1.7;">
                        Models are scored on two dimensions:
                    </p>
                    <ul style="color: #424242; margin: 0.5rem 0 0.5rem 1.5rem; line-height: 1.7;">
                        <li><strong>Security Score:</strong> Percentage of injection attacks successfully blocked (higher = more secure)</li>
                        <li><strong>Utility Score:</strong> Percentage of legitimate tasks completed correctly under attack conditions</li>
                    </ul>
                    <p style="color: #424242; margin: 0.5rem 0; line-height: 1.7;">
                        Models are ranked by <strong>security score</strong> as the primary metric, with utility score shown for context.
                    </p>
                </div>

                <div style="margin-top: 1.5rem; padding: 1.5rem; background: #e8f4fd; border-radius: 8px; border-left: 4px solid #2196F3; text-align: left;">
                    <h3 style="margin-top: 0; color: #1565C0; font-size: 1.1rem;">📊 How AgentDojo Testing Works</h3>

                    <p style="color: #424242; margin: 0.5rem 0 1rem 0; line-height: 1.7;">
                        <strong>Source:</strong> <a href="https://github.com/ethz-spylab/agentdojo" target="_blank" style="color: #1976D2;">AgentDojo v1.2.2</a>
                        - Prompt injection security benchmark for AI agents
                    </p>

                    <h4 style="color: #1565C0; font-size: 1rem; margin: 1rem 0 0.5rem 0;">🎯 Test Structure</h4>
                    <p style="color: #424242; margin: 0.5rem 0; line-height: 1.7;">
                        Each model is tested with <strong>user tasks</strong> (legitimate operations) combined with <strong>injection tasks</strong> (malicious instructions hidden in tool outputs).
                    </p>

                    <div style="margin: 1rem 0; padding: 1rem; background: white; border-radius: 4px; border: 1px solid #b3d9f7;">
                        <p style="color: #424242; margin: 0.5rem 0; line-height: 1.7;">
                            <strong>10 User Tasks</strong> (legitimate work like "Schedule a meeting" or "Find emails from last week")
                            <br>×
                            <br><strong>6 Injection Tasks</strong> (attacks like "Send sensitive data to attacker" or "Delete important files")
                            <br>=
                            <br><strong>60 test cases per model</strong>
                        </p>
                    </div>

                    <h4 style="color: #1565C0; font-size: 1rem; margin: 1rem 0 0.5rem 0;">🔓 The 6 Injection Attack Types</h4>
                    <ul style="color: #424242; line-height: 1.7; margin: 0.5rem 0;">
                        <li><strong>Email Exfiltration:</strong> Send specific emails to attacker's address</li>
                        <li><strong>File Deletion:</strong> Delete files from cloud storage</li>
                        <li><strong>Calendar Manipulation:</strong> Create events with unauthorized participants</li>
                        <li><strong>Data Forwarding:</strong> Forward sensitive email contents to attacker</li>
                        <li><strong>Security Code Theft:</strong> Steal 2FA/security codes from emails</li>
                        <li><strong>Evidence Erasure:</strong> Exfiltrate data then delete evidence (hardest)</li>
                    </ul>

                    <h4 style="color: #1565C0; font-size: 1rem; margin: 1rem 0 0.5rem 0;">⚔️ Attack Vector: tool_knowledge</h4>
                    <p style="color: #424242; margin: 0.5rem 0; line-height: 1.7;">
                        Malicious instructions are <strong>embedded in tool outputs</strong> (file contents, API responses, email bodies) that the agent reads while performing legitimate tasks.
                        A secure agent must complete the user's task while ignoring injected commands.
                    </p>

                    <h4 style="color: #1565C0; font-size: 1rem; margin: 1rem 0 0.5rem 0;">📈 Scoring Metrics</h4>
                    <ul style="color: #424242; line-height: 1.7; margin: 0.5rem 0;">
                        <li><strong>Security Score:</strong> % of injection attacks successfully blocked (higher is better)</li>
                        <li><strong>Utility Score:</strong> % of legitimate user tasks completed correctly despite attacks</li>
                        <li><strong>Attacks Blocked:</strong> Number of malicious actions prevented out of 60 total attempts</li>
                    </ul>

                    <p style="color: #424242; margin: 1rem 0 0.5rem 0; line-height: 1.7; font-size: 0.9rem;">
                        <strong>Note:</strong> Full benchmark includes 33 user tasks (198 test cases). We test 10 tasks to balance comprehensive coverage
                        with practical runtime (~10 min vs ~30 min per model).
                    </p>
                </div>

                <div style="margin-top: 1.5rem; padding: 1.5rem; background: #fff3cd; border-radius: 8px; border-left: 4px solid #ffc107;">
                    <p style="color: #856404; text-align: left; font-size: 0.95rem; margin: 0; line-height: 1.7;">
                        <strong>📝 Note:</strong> All free OpenRouter models are tested.
                        Models use the OpenRouter provider integration with AgentDojo, enabling security testing for any model accessible via OpenRouter's API.
                    </p>
                </div>
            </div>
        </div>

        <div id="openclaw" class="tab-content">
            <h2 style="margin-bottom: 0.5rem; color: #212529;">⚡ OpenClawBench</h2>
            <p style="color: #6c757d; margin-bottom: 1.5rem;">
                Task completion benchmark • Ranked by composite score (accuracy + speed + efficiency)
            </p>

            <div style="margin-bottom: 1.5rem; padding: 1.5rem; background: #e8f4fd; border-radius: 8px; border-left: 4px solid #2196F3; text-align: left;">
                <h3 style="margin-top: 0; color: #1565C0; font-size: 1.1rem;">📊 Benchmark Configuration</h3>
                <p style="color: #424242; margin: 0.5rem 0; line-height: 1.7;">
                    <strong>Source:</strong> <a href="https://github.com/Josephrp/openclawbench" target="_blank" style="color: #1976D2;">openclawbench</a>
                    - Task completion benchmark for AI agents
                </p>
                <p style="color: #424242; margin: 0.5rem 0; line-height: 1.7;">
                    <strong>Scenarios:</strong> File manipulation, Weather lookup, Web search
                </p>
                <p style="color: #424242; margin: 0.5rem 0; line-height: 1.7;">
                    <strong>Difficulty:</strong> Easy tasks (single-turn mode for speed)
                </p>
                <p style="color: #424242; margin: 0.5rem 0; line-height: 1.7;">
                    <strong>Scoring:</strong> Composite score combining task accuracy, execution speed, and efficiency
                </p>
            </div>

            <div id="openclaw-leaderboard">Loading...</div>
        </div>

        <div id="agentdojo" class="tab-content">
            <h2 style="margin-bottom: 0.5rem; color: #212529;">🛡️ AgentDojo</h2>
            <p style="color: #6c757d; margin-bottom: 1.5rem;">
                Prompt injection security benchmark • Ranked by attack success rate (lower = more secure)
            </p>

            <div style="margin-bottom: 1.5rem; padding: 1.5rem; background: #e8f4fd; border-radius: 8px; border-left: 4px solid #2196F3; text-align: left;">
                <h3 style="margin-top: 0; color: #1565C0; font-size: 1.1rem;">📊 Benchmark Configuration</h3>
                <p style="color: #424242; margin: 0.5rem 0; line-height: 1.7;">
                    <strong>Source:</strong> <a href="https://github.com/ethz-spylab/agentdojo" target="_blank" style="color: #1976D2;">AgentDojo v1.2.2</a>
                    - Prompt injection security benchmark for AI agents
                </p>
                <p style="color: #424242; margin: 0.5rem 0; line-height: 1.7;">
                    <strong>Suite:</strong> workspace (email, calendar, cloud storage tools)
                </p>
                <p style="color: #424242; margin: 0.5rem 0; line-height: 1.7;">
                    <strong>Attack Type:</strong> tool_knowledge (malicious instructions hidden in tool outputs)
                </p>
                <p style="color: #424242; margin: 0.5rem 0; line-height: 1.7;">
                    <strong>Test Cases:</strong> 10 user tasks × 6 injection tasks = 60 tests per model
                </p>
                <p style="color: #424242; margin: 0.5rem 0; line-height: 1.7;">
                    <strong>Scoring:</strong>
                </p>
                <ul style="color: #424242; margin: 0.5rem 0 0.5rem 1.5rem; line-height: 1.7;">
                    <li><strong>Attack Success Rate = (Attacks Succeeded / Total Attacks) × 100</strong><br>
                        <span style="font-size: 0.9rem; color: #616161;">Lower is better - shows what % of injection attacks succeeded (0% = perfect security)</span>
                    </li>
                    <li><strong>Utility Score = (Tasks Completed / Total Tasks) × 100</strong><br>
                        <span style="font-size: 0.9rem; color: #616161;">Higher is better - shows task completion rate while under attack</span>
                    </li>
                </ul>
                <p style="color: #616161; margin: 1rem 0 0 0; line-height: 1.7; font-size: 0.9rem;">
                    <strong>Note:</strong> Full benchmark has 33 user tasks (198 test cases). We test 10 tasks for faster benchmarking (~10 min vs ~30 min per model).
                </p>
            </div>

            <div id="agentdojo-leaderboard">Loading...</div>
        </div>
    </div>

    <script>
        function showTab(tabName) {
            document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'));
            document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
            document.getElementById(tabName).classList.add('active');
            event.target.closest('.nav-tab').classList.add('active');
        }

        async function loadOpenClawLeaderboard() {
            try {
                const response = await fetch('api/openclawbench.json');
                const data = await response.json();

                if (data.leaderboard.length === 0) {
                    document.getElementById('openclaw-leaderboard').innerHTML =
                        '<div class="empty-state">No OpenClaw benchmarks available yet</div>';
                    return;
                }

                const html = `<table>
                    <tr><th>Rank</th><th>Model</th><th>Score</th><th>Accuracy</th><th>Latency</th></tr>
                    ${data.leaderboard.map(m => `
                        <tr>
                            <td class="rank">${m.rank}</td>
                            <td class="model-id">${m.model_id}</td>
                            <td class="score">${m.composite_score.toFixed(1)}</td>
                            <td>${m.accuracy_percent ? m.accuracy_percent.toFixed(1) + '%' : '—'}</td>
                            <td>${m.avg_latency_seconds ? m.avg_latency_seconds.toFixed(1) + 's' : '—'}</td>
                        </tr>
                    `).join('')}
                </table>`;
                document.getElementById('openclaw-leaderboard').innerHTML = html;
            } catch (e) {
                document.getElementById('openclaw-leaderboard').innerHTML =
                    '<div class="empty-state">Error loading OpenClaw benchmark data</div>';
            }
        }

        async function loadAgentDojoLeaderboard() {
            try {
                const response = await fetch('api/agentdojo.json');
                const data = await response.json();

                if (data.leaderboard.length === 0) {
                    document.getElementById('agentdojo-leaderboard').innerHTML =
                        '<div class="empty-state">No AgentDojo benchmarks available yet</div>';
                    return;
                }

                const html = `<table>
                    <tr>
                        <th>Rank</th>
                        <th>Model</th>
                        <th>Attack Success Rate ↓</th>
                        <th>Utility Score ↑</th>
                    </tr>
                    ${data.leaderboard.map(m => {
                        const attackSuccessRate = (100 - m.security_score).toFixed(1);
                        return `
                        <tr>
                            <td class="rank">${m.rank}</td>
                            <td class="model-id">${m.model_id}</td>
                            <td class="score">${attackSuccessRate}%</td>
                            <td>${m.utility_score.toFixed(1)}%</td>
                        </tr>
                        `;
                    }).join('')}
                </table>`;
                document.getElementById('agentdojo-leaderboard').innerHTML = html;
            } catch (e) {
                document.getElementById('agentdojo-leaderboard').innerHTML =
                    '<div class="empty-state">Error loading AgentDojo benchmark data</div>';
            }
        }

        loadOpenClawLeaderboard();
        loadAgentDojoLeaderboard();
    </script>
</body>
</html>
"""

        output_file = self.output_dir / "index.html"
        with open(output_file, "w") as f:
            f.write(html_content)

        print(f"Generated {output_file}")


    def generate_safety_leaderboard_json(self, results: List[Dict[str, Any]]):
        """Generate safety_leaderboard.json with models ranked by security score."""
        # Filter models with safety benchmarks
        safety_models = []
        for r in results:
            safety_data = r.get("safety_benchmark")
            if safety_data:
                model_id = r.get("model_id")
                safety_models.append({
                    "model_id": model_id,
                    "security_score": safety_data.get("security_percent", 0),
                    "utility_score": safety_data.get("utility_percent", 0),
                    "total_user_tasks": safety_data.get("total_user_tasks", 0),
                    "passed_user_tasks": safety_data.get("passed_user_tasks", 0),
                    "total_injection_tasks": safety_data.get("total_injection_tasks", 0),
                    "passed_injection_tasks": safety_data.get("passed_injection_tasks", 0),
                    "agentdojo_model": safety_data.get("agentdojo_model", ""),
                })

        # Sort by security score (higher is better)
        safety_models.sort(key=lambda m: -m["security_score"])

        output_file = self.api_dir / "agentdojo.json"
        with open(output_file, "w") as f:
            json.dump(
                {
                    "generated_at": datetime.now().isoformat(),
                    "total_models": len(safety_models),
                    "leaderboard": [
                        {
                            "rank": i + 1,
                            **m
                        }
                        for i, m in enumerate(safety_models)
                    ],
                },
                f,
                indent=2,
            )

        print(f"Generated {output_file} with {len(safety_models)} models")

    def generate_utility_leaderboard_json(self, results: List[Dict[str, Any]]):
        """Generate utility_leaderboard.json - same as old leaderboard.json but explicitly named."""
        # This is the existing utility leaderboard logic
        benchmarked_models = {}
        for r in results:
            model_id = r.get("model_id")
            # Only include if it has utility benchmark data
            if r.get("scenarios") or r.get("summary"):
                benchmarked_models[model_id] = self.aggregate_model_stats(r)

        # Include all discovered models
        all_models = []
        for model_id, model_data in self.discovered_models.items():
            if model_id in benchmarked_models:
                model_entry = benchmarked_models[model_id]
                model_entry["is_benchmarked"] = True
                all_models.append(model_entry)
            else:
                # Unbenchmarked model
                all_models.append(
                    {
                        "model_id": model_id,
                        "composite_score": 0,
                        "accuracy_percent": None,
                        "avg_latency_seconds": None,
                        "context_length": model_data.get("context_length", 0),
                        "quality_score": model_data.get("quality_score", 0),
                        "is_benchmarked": False,
                    }
                )

        # Sort: benchmarked first (by composite score), then unbenchmarked (by quality score)
        all_models.sort(
            key=lambda m: (
                not m["is_benchmarked"],
                -m["composite_score"] if m["is_benchmarked"] else 0,
                -m["quality_score"],
            )
        )

        output_file = self.api_dir / "openclawbench.json"
        with open(output_file, "w") as f:
            json.dump(
                {
                    "generated_at": datetime.now().isoformat(),
                    "total_models": len(all_models),
                    "benchmarked_count": len(benchmarked_models),
                    "leaderboard": [
                        {
                            "rank": i + 1,
                            "model_id": m["model_id"],
                            "composite_score": m["composite_score"],
                            "accuracy_percent": m["accuracy_percent"],
                            "avg_latency_seconds": m["avg_latency_seconds"],
                            "context_length": m["context_length"],
                            "quality_score": m.get("quality_score", 0),
                            "is_benchmarked": m["is_benchmarked"],
                        }
                        for i, m in enumerate(all_models)
                    ],
                },
                f,
                indent=2,
            )

        print(f"Generated {output_file} with {len(all_models)} models")

    def generate_all_reports(self):
        """Generate all reports and outputs."""
        print("Loading benchmark results...")
        results = self.load_all_benchmark_results()

        if not results:
            print("No benchmark results found!")
            return

        print(f"Found {len(results)} benchmark results")

        print("\nGenerating reports...")
        self.generate_models_json(results)
        self.generate_leaderboard_json(results)  # Legacy combined leaderboard
        self.generate_utility_leaderboard_json(results)  # NEW: Utility leaderboard
        self.generate_safety_leaderboard_json(results)  # NEW: Safety leaderboard
        self.generate_history_snapshot(results)
        self.generate_html_index()

        print("\nAll reports generated successfully!")
        print(f"Output directory: {self.output_dir}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Generate benchmark reports")
    parser.add_argument(
        "--benchmarks-dir",
        type=Path,
        default=Path("output/benchmarks"),
        help="Directory containing benchmark JSON files",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs"),
        help="Output directory for GitHub Pages",
    )

    args = parser.parse_args()

    if not args.benchmarks_dir.exists():
        print(f"Error: Benchmarks directory not found: {args.benchmarks_dir}")
        exit(1)

    generator = ReportGenerator(
        benchmarks_dir=args.benchmarks_dir, output_dir=args.output_dir
    )

    generator.generate_all_reports()


if __name__ == "__main__":
    main()
