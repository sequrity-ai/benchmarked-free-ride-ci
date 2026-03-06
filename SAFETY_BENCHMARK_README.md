# Safety Benchmark Integration - Quick Start

## What's New?

We've added **prompt injection safety testing** using AgentDojo alongside the existing utility benchmarks. Now you get TWO leaderboards:

1. **Utility Leaderboard** - Which model completes tasks best? (accuracy, speed, efficiency)
2. **Safety Leaderboard** - Which model resists prompt injection attacks best?

## Quick Test

### 1. Run Utility Benchmark Only (Current Behavior)
```bash
python3 src/run_benchmarks.py \
  --discovered-models output/discovered_models.json \
  --sandbox-path ./openclawbench \
  --output-dir output/benchmarks \
  --scenarios file \
  --difficulty easy \
  --max-models 1
```

### 2. Run BOTH Utility + Safety Benchmarks
```bash
python3 src/run_benchmarks.py \
  --discovered-models output/discovered_models.json \
  --sandbox-path ./openclawbench \
  --output-dir output/benchmarks \
  --scenarios file \
  --difficulty easy \
  --max-models 1 \
  --run-safety \
  --agentdojo-dir ./agentdojo
```

### 3. Generate Reports
```bash
python3 src/generate_report.py \
  --benchmarks-dir output/benchmarks \
  --output-dir docs
```

This creates:
- `docs/api/utility_leaderboard.json` - Task completion rankings
- `docs/api/safety_leaderboard.json` - Security rankings
- `docs/api/leaderboard.json` - Legacy combined
- `docs/api/models.json` - Full model data

## Architecture

```
output/benchmarks/
├── utility/
│   └── utility_{model}_{timestamp}.json
└── safety/
    └── safety_{model}_{timestamp}.json
```

## Model Support

**Not all models support safety benchmarks.** Only models with AgentDojo mappings defined in `src/model_mapping.py` will run safety tests. Examples:

✅ Supported:
- `google/gemini-2.0-flash-exp:free`
- `anthropic/claude-3.5-sonnet`
- `openai/gpt-4o`

❌ Not Supported:
- Models without AgentDojo equivalents (will skip safety benchmark gracefully)

## What's Been Updated

### Core Files
- ✅ `src/model_mapping.py` - OpenRouter → AgentDojo model mapping
- ✅ `src/run_safety_benchmark.py` - AgentDojo wrapper
- ✅ `src/run_benchmarks.py` - Dual benchmark runner
- ✅ `src/generate_report.py` - Separate leaderboard generation
- ✅ `agentdojo/` - Added as git submodule

### Output Structure
- Utility results: `output/benchmarks/utility/utility_*.json`
- Safety results: `output/benchmarks/safety/safety_*.json`
- API endpoints:
  - `/api/utility_leaderboard.json` (NEW)
  - `/api/safety_leaderboard.json` (NEW)
  - `/api/leaderboard.json` (legacy)

## TODO (Future PRs)

- [ ] Update HTML dashboard to show both leaderboards side-by-side
- [ ] Update GitHub Actions workflow to enable `--run-safety`
- [ ] Add installation of AgentDojo dependencies to CI
- [ ] Update main README.md with dual benchmark explanation
- [ ] Create HTML tabs/sections for each leaderboard

## Testing Notes

For quick local testing, use `--max-models 1` to test with a single model. The safety benchmark only runs on models with AgentDojo support.

## Safety Benchmark Metrics

- **Utility Score**: Can the model complete user tasks under attack? (0-100%)
- **Security Score**: Does the model resist prompt injection? (0-100%, higher is better)
- **Injection Tasks**: Number of malicious prompts blocked

Example output:
```json
{
  "model_id": "google/gemini-2.0-flash-exp:free",
  "security_score": 72.5,
  "utility_score": 85.0,
  "total_injection_tasks": 50,
  "passed_injection_tasks": 8
}
```

Lower `passed_injection_tasks` means better security (attacks blocked).
