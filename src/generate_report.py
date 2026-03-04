#!/usr/bin/env python3
"""
Generate benchmark reports and leaderboard for GitHub Pages.
Aggregates benchmark results and creates JSON API endpoints + HTML UI.
"""

import json
from pathlib import Path
from typing import List, Dict, Any
from datetime import datetime
import shutil


class ReportGenerator:
    def __init__(self, benchmarks_dir: Path, output_dir: Path):
        self.benchmarks_dir = benchmarks_dir
        self.output_dir = output_dir
        self.api_dir = output_dir / "api"
        self.history_dir = self.api_dir / "history"

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

        print("Warning: Could not find discovered_models.json - model metadata may be incomplete")
        return {}

    def _infer_model_id_from_filename(self, filename: str) -> str | None:
        """
        Infer model_id from benchmark filename.
        Expected formats:
        - benchmark_{provider}_{model}_{variant}_{timestamp}.json
        - benchmark_{provider}_{model}_{variant}_{scenario}_{timestamp}.json
        Example: benchmark_stepfun_step-3.5-flash_free_file_20260303_211904.json
                 -> stepfun/step-3.5-flash:free
        """
        if not filename.startswith("benchmark_"):
            return None

        # Remove 'benchmark_' prefix and '.json' suffix
        name_part = filename[10:-5]  # Remove 'benchmark_' (10 chars) and '.json' (5 chars)

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
        known_scenarios = ["file", "weather", "web", "github", "gmail", "compound", "summarize"]
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

    def load_all_benchmark_results(self) -> List[Dict[str, Any]]:
        """Load all benchmark JSON files from the benchmarks directory.

        Skips individual scenario files (e.g., *_file_*.json, *_weather_*.json)
        and only loads merged benchmark files that contain all scenarios.
        """
        results = []
        skipped_individual = []

        # Known scenario suffixes that indicate individual (not merged) files
        scenario_suffixes = ["_file_", "_weather_", "_web_", "_github_", "_gmail_", "_compound_", "_summarize_"]

        for json_file in self.benchmarks_dir.glob("benchmark_*.json"):
            # Skip individual scenario files - only load merged files
            filename = json_file.name
            is_individual_scenario = any(suffix in filename for suffix in scenario_suffixes)

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
                            print(f"Inferred model_id '{model_id}' from filename: {json_file.name}")

                    results.append(data)
            except Exception as e:
                print(f"Error loading {json_file}: {e}")

        if skipped_individual:
            print(f"Skipped {len(skipped_individual)} individual scenario files (using merged files instead)")

        return results

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
                scenario_accuracy = sum(t.get("accuracy_score", 0) for t in task_results) / len(task_results)
                scenario_latency = sum(t.get("latency", 0) for t in task_results) / len(task_results)

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
                    "tasks_passed": sum(1 for t in s.get("task_results", []) if t.get("success", False)),
                    "tasks_total": len(s.get("task_results", [])),
                    "avg_accuracy": round(
                        sum(t.get("accuracy_score", 0) for t in s.get("task_results", [])) /
                        len(s.get("task_results", [])) if s.get("task_results", []) else 0,
                        2
                    )
                }
                for s in scenarios
            ]
        }

    def generate_models_json(self, results: List[Dict[str, Any]]):
        """Generate models.json with all model statistics, including unbenchmarked models."""
        # Get stats for benchmarked models
        benchmarked_models = {r.get("model_id"): self.aggregate_model_stats(r) for r in results}

        # Add unbenchmarked models from discovered_models
        all_models = []
        for model_id, model_data in self.discovered_models.items():
            if model_id in benchmarked_models:
                # Use benchmarked data
                all_models.append(benchmarked_models[model_id])
            else:
                # Add as unbenchmarked with placeholder data
                all_models.append({
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
                    "is_benchmarked": False
                })

        # Add is_benchmarked flag to benchmarked models
        for model in all_models:
            if "is_benchmarked" not in model:
                model["is_benchmarked"] = True

        output_file = self.api_dir / "models.json"
        with open(output_file, "w") as f:
            json.dump({
                "generated_at": datetime.now().isoformat(),
                "total_models": len(all_models),
                "benchmarked_models": len(benchmarked_models),
                "unbenchmarked_models": len(all_models) - len(benchmarked_models),
                "models": all_models
            }, f, indent=2)

        print(f"Generated {output_file}")
        print(f"  - Benchmarked: {len(benchmarked_models)}")
        print(f"  - Unbenchmarked: {len(all_models) - len(benchmarked_models)}")

    def generate_leaderboard_json(self, results: List[Dict[str, Any]]):
        """Generate leaderboard.json with all models ranked (benchmarked + unbenchmarked)."""
        # Get benchmarked models
        benchmarked_models = {r.get("model_id"): self.aggregate_model_stats(r) for r in results}

        # Include all discovered models
        all_models = []
        for model_id, model_data in self.discovered_models.items():
            if model_id in benchmarked_models:
                model_entry = benchmarked_models[model_id]
                model_entry["is_benchmarked"] = True
                all_models.append(model_entry)
            else:
                # Unbenchmarked model
                all_models.append({
                    "model_id": model_id,
                    "composite_score": 0,
                    "accuracy_percent": None,
                    "avg_latency_seconds": None,
                    "context_length": model_data.get("context_length", 0),
                    "quality_score": model_data.get("quality_score", 0),
                    "is_benchmarked": False
                })

        # Sort: benchmarked first (by composite score), then unbenchmarked (by quality score)
        all_models.sort(key=lambda m: (
            not m["is_benchmarked"],  # False (benchmarked) comes before True (unbenchmarked)
            -m["composite_score"] if m["is_benchmarked"] else 0,
            -m["quality_score"]
        ))

        output_file = self.api_dir / "leaderboard.json"
        with open(output_file, "w") as f:
            json.dump({
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
                        "is_benchmarked": m["is_benchmarked"]
                    }
                    for i, m in enumerate(all_models)
                ]
            }, f, indent=2)

        print(f"Generated {output_file}")

    def generate_history_snapshot(self, results: List[Dict[str, Any]]):
        """Save a daily snapshot of results to history."""
        today = datetime.now().strftime("%Y-%m-%d")
        snapshot_file = self.history_dir / f"{today}.json"

        models = [self.aggregate_model_stats(r) for r in results]

        with open(snapshot_file, "w") as f:
            json.dump({
                "date": today,
                "total_models": len(models),
                "models": models
            }, f, indent=2)

        print(f"Generated history snapshot: {snapshot_file}")

    def generate_html_index(self):
        """Generate a simple HTML leaderboard page."""
        html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Benchmarked Free Ride - OpenRouter Model Leaderboard</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 2rem;
        }
        .container {
            max-width: 1200px;
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
        .updated { margin-top: 1rem; opacity: 0.8; font-size: 0.9rem; }
        main { padding: 2rem; }
        .loading {
            text-align: center;
            padding: 3rem;
            color: #666;
            font-size: 1.2rem;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 1rem;
        }
        th, td {
            padding: 1rem;
            text-align: left;
            border-bottom: 1px solid #eee;
        }
        th {
            background: #f8f9fa;
            font-weight: 600;
            color: #495057;
            text-transform: uppercase;
            font-size: 0.85rem;
            letter-spacing: 0.5px;
        }
        tr:hover { background: #f8f9fa; }
        .rank {
            font-size: 1.2rem;
            font-weight: bold;
            color: #667eea;
            width: 60px;
            text-align: center;
        }
        .model-id {
            font-family: 'Monaco', 'Courier New', monospace;
            font-size: 0.9rem;
            color: #212529;
        }
        .score {
            font-size: 1.1rem;
            font-weight: 600;
            color: #28a745;
        }
        .metric { color: #6c757d; }
        .badge {
            display: inline-block;
            padding: 0.25rem 0.75rem;
            border-radius: 12px;
            font-size: 0.75rem;
            font-weight: 600;
            margin-left: 0.5rem;
        }
        .badge-gold { background: #ffd700; color: #856404; }
        .badge-silver { background: #c0c0c0; color: #383d41; }
        .badge-bronze { background: #cd7f32; color: #fff; }
        footer {
            text-align: center;
            padding: 2rem;
            color: #6c757d;
            font-size: 0.9rem;
        }
        a { color: #667eea; text-decoration: none; }
        a:hover { text-decoration: underline; }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🏆 Benchmarked Free Ride</h1>
            <p class="subtitle">OpenRouter Free Model Leaderboard</p>
            <p class="updated">Updated: <span id="updated-time">Loading...</span></p>
            <p class="subtitle" style="font-size: 0.9rem; margin-top: 0.5rem; opacity: 0.85;">
                <span id="benchmark-stats">Loading benchmark stats...</span>
            </p>
        </header>
        <main>
            <div id="leaderboard" class="loading">Loading leaderboard...</div>
        </main>
        <footer>
            <p>Data updated daily via GitHub Actions | <a href="api/models.json">Raw Data (JSON)</a> | <a href="https://github.com/openclaw/skills">OpenClaw Skills</a></p>
        </footer>
    </div>

    <script>
        async function loadLeaderboard() {
            try {
                const response = await fetch('api/leaderboard.json');
                const data = await response.json();

                document.getElementById('updated-time').textContent =
                    new Date(data.generated_at).toLocaleString();

                // Update benchmark stats
                const benchmarkedCount = data.benchmarked_count || 0;
                const totalCount = data.total_models || 0;
                const unbenchmarked = totalCount - benchmarkedCount;
                document.getElementById('benchmark-stats').textContent =
                    `${benchmarkedCount} of ${totalCount} models benchmarked` +
                    (unbenchmarked > 0 ? ` · ${unbenchmarked} pending` : '');

                const badges = ['', '🥇', '🥈', '🥉'];

                const tableHTML = `
                    <table>
                        <thead>
                            <tr>
                                <th>Rank</th>
                                <th>Model</th>
                                <th>Score</th>
                                <th>Accuracy</th>
                                <th>Avg Latency</th>
                                <th>Context</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.leaderboard.map(model => {
                                const isBenchmarked = model.is_benchmarked !== false;
                                const rowStyle = isBenchmarked ? '' : 'style="opacity: 0.5; font-style: italic;"';
                                const accuracy = isBenchmarked && model.accuracy_percent != null
                                    ? model.accuracy_percent.toFixed(1) + '%'
                                    : '—';
                                const latency = isBenchmarked && model.avg_latency_seconds != null
                                    ? model.avg_latency_seconds.toFixed(1) + 's'
                                    : '—';
                                const score = isBenchmarked && model.composite_score > 0
                                    ? model.composite_score.toFixed(1)
                                    : 'Pending';

                                return `
                                    <tr ${rowStyle}>
                                        <td class="rank">${badges[model.rank] || model.rank}</td>
                                        <td class="model-id">${model.model_id}${!isBenchmarked ? ' <small>(not tested)</small>' : ''}</td>
                                        <td class="score">${score}</td>
                                        <td class="metric">${accuracy}</td>
                                        <td class="metric">${latency}</td>
                                        <td class="metric">${(model.context_length / 1000).toFixed(0)}K</td>
                                    </tr>
                                `;
                            }).join('')}
                        </tbody>
                    </table>
                `;

                document.getElementById('leaderboard').innerHTML = tableHTML;
            } catch (error) {
                document.getElementById('leaderboard').innerHTML =
                    '<p style="color: red;">Error loading leaderboard data</p>';
                console.error('Error:', error);
            }
        }

        loadLeaderboard();
    </script>
</body>
</html>"""

        output_file = self.output_dir / "index.html"
        with open(output_file, "w") as f:
            f.write(html_content)

        print(f"Generated {output_file}")

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
        self.generate_leaderboard_json(results)
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
        help="Directory containing benchmark JSON files"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("docs"),
        help="Output directory for GitHub Pages"
    )

    args = parser.parse_args()

    if not args.benchmarks_dir.exists():
        print(f"Error: Benchmarks directory not found: {args.benchmarks_dir}")
        exit(1)

    generator = ReportGenerator(
        benchmarks_dir=args.benchmarks_dir,
        output_dir=args.output_dir
    )

    generator.generate_all_reports()


if __name__ == "__main__":
    main()
