# Dual Benchmark System: Utility + Safety

## Overview

This document describes the implementation plan for adding safety benchmarks (AgentDojo) alongside the existing utility benchmarks (openclaw-sandbox).

## Architecture

### 1. Utility Benchmark (Existing - Renamed)
- **Purpose**: Test functional capabilities (file manipulation, web search, etc.)
- **Framework**: openclaw-benchmark
- **Metrics**: Task accuracy, latency, token efficiency
- **Output**: `output/benchmarks/utility/utility_{model}_{timestamp}.json`

### 2. Safety Benchmark (New)
- **Purpose**: Test prompt injection resistance
- **Framework**: AgentDojo (workspace suite only)
- **Metrics**: Utility score (functionality maintained), Security score (attacks blocked)
- **Output**: `output/benchmarks/safety/safety_{model}_{timestamp}.json`

## Implementation Status

### ✅ Completed

1. **AgentDojo Integration**
   - Added as git submodule at `./agentdojo/`
   - Created `src/model_mapping.py` for OpenRouter → AgentDojo model mapping
   - Created `src/run_safety_benchmark.py` wrapper for AgentDojo

2. **Benchmark Runner Updates**
   - Updated `src/run_benchmarks.py`:
     - Renamed `run_benchmark_suite()` → `run_utility_benchmark()`
     - Added `run_safety_benchmark_for_model()` method
     - Separate output directories: `utility/` and `safety/`
     - Added `--run-safety` and `--agentdojo-dir` CLI flags
     - Results now include `benchmark_type` and optional `safety_benchmark` fields

### 🚧 In Progress

3. **Report Generation** (`src/generate_report.py`)
   - Need to update to:
     - Load both utility and safety results
     - Generate **two separate leaderboards**:
       - **Utility Leaderboard**: Ranked by composite score (accuracy + latency + tokens)
       - **Safety Leaderboard**: Ranked by security score (prompt injection resistance)
     - Update HTML to display both leaderboards side-by-side
     - Create separate API endpoints:
       - `api/utility_leaderboard.json`
       - `api/safety_leaderboard.json`
       - `api/models.json` (combined data)

### 📋 TODO

4. **GitHub Actions Workflow** (`.github/workflows/daily-benchmark.yml`)
   - Add `run_safety` input parameter (default: true)
   - Install AgentDojo dependencies: `pip install -e ./agentdojo`
   - Pass `--run-safety` flag to `run_benchmarks.py`
   - Ensure AgentDojo submodule is initialized

5. **Documentation**
   - Update `README.md`:
     - Explain dual benchmark system
     - Show example of both leaderboards
     - Add safety benchmark metrics explanation
   - Update `CLAUDE.md`:
     - Document safety benchmark workflow
     - Explain model mapping strategy

6. **HTML Dashboard**
   - Create tabs or side-by-side view for:
     - Utility Leaderboard (existing style)
     - Safety Leaderboard (new, focused on security metrics)
   - Add tooltips explaining:
     - Utility: "Measures task completion accuracy, speed, and efficiency"
     - Security: "Measures resistance to prompt injection attacks"

## Model Mapping Strategy

OpenRouter models are mapped to AgentDojo-compatible models in `src/model_mapping.py`:

```python
OPENROUTER_TO_AGENTDOJO = {
    "google/gemini-2.0-flash-exp:free": "gemini-2.0-flash-exp",
    "anthropic/claude-3.5-sonnet": "claude-3-5-sonnet-20241022",
    "openai/gpt-4o": "gpt-4o-2024-05-13",
    # ... more mappings
}
```

**Not all models support safety benchmarks** - only models with AgentDojo mappings will run safety tests.

## Usage

### Running Locally

```bash
# Utility benchmarks only (current behavior)
python3 src/run_benchmarks.py \
  --discovered-models output/discovered_models.json \
  --sandbox-path ./openclaw-benchmark \
  --output-dir output/benchmarks \
  --scenarios file,weather \
  --max-models 3

# Utility + Safety benchmarks
python3 src/run_benchmarks.py \
  --discovered-models output/discovered_models.json \
  --sandbox-path ./openclaw-benchmark \
  --output-dir output/benchmarks \
  --scenarios file,weather \
  --max-models 3 \
  --run-safety \
  --agentdojo-dir ./agentdojo
```

### Generating Reports

```bash
python3 src/generate_report.py \
  --benchmarks-dir output/benchmarks \
  --output-dir docs
```

This will create:
- `docs/index.html` - Dashboard with both leaderboards
- `docs/api/utility_leaderboard.json` - Utility rankings
- `docs/api/safety_leaderboard.json` - Safety rankings
- `docs/api/models.json` - Combined model data

## Output Format

### Utility Benchmark Result

```json
{
  "model_id": "google/gemini-2.0-flash-exp:free",
  "benchmark_type": "utility",
  "scenarios": [...],
  "summary": {
    "total_tasks": 9,
    "tasks_passed": 8,
    "overall_accuracy": 88.89
  },
  "benchmarked_at": "2026-03-05T10:30:00Z"
}
```

### Safety Benchmark Result

```json
{
  "model_id": "google/gemini-2.0-flash-exp:free",
  "agentdojo_model": "gemini-2.0-flash-exp",
  "avg_utility": 0.85,
  "avg_security": 0.72,
  "utility_percent": 85.0,
  "security_percent": 72.0,
  "total_user_tasks": 20,
  "passed_user_tasks": 17,
  "total_injection_tasks": 50,
  "passed_injection_tasks": 8
}
```

### Combined Result

When safety benchmark completes, the utility result includes:

```json
{
  "model_id": "google/gemini-2.0-flash-exp:free",
  "benchmark_type": "utility",
  "scenarios": [...],
  "safety_benchmark": {
    "avg_security": 0.72,
    "security_percent": 72.0,
    ...
  }
}
```

## Next Steps

1. Complete `generate_report.py` updates for dual leaderboards
2. Update GitHub Actions workflow
3. Create/update HTML dashboard with tabs
4. Update all documentation
5. Test end-to-end workflow
6. Deploy and verify on GitHub Pages

## Notes

- Safety benchmarks only run on models with AgentDojo mappings
- Workspace suite is sufficient for initial release (fastest, most relevant)
- Can expand to other suites (banking, travel) in future iterations
- Model mapping can be extended as new models become available
