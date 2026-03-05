# Benchmarked Free Ride CI

Automated daily benchmarking of free OpenRouter models with quality scoring and public leaderboard.

## What This Does

This repository automatically:

1. **Discovers** free models from OpenRouter API (like [FreeRide](https://github.com/openclaw/skills/tree/main/skills/shaivpidadi/free-ride))
2. **Benchmarks** them using the [openclaw-benchmark](https://github.com/sequrity-ai/openclaw-benchmark) test suite
3. **Scores** models based on accuracy, latency, and token efficiency
4. **Publishes** results to a public GitHub Pages leaderboard with JSON API

The companion skill [benchmarked-free-ride-skill](https://github.com/sequrity-ai/benchmarked-free-ride-skill) lets you fetch these scores and auto-configure the best free model.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│           GitHub Actions (Daily at 2 AM UTC)                │
│                                                              │
│  1. Discover Free Models (OpenRouter API)                   │
│       ↓                                                      │
│  2. Run Benchmarks (openclaw-benchmark, single-turn mode)   │
│       ↓                                                      │
│  3. Calculate Quality Scores (accuracy + latency + tokens)  │
│       ↓                                                      │
│  4. Generate Reports (JSON + HTML)                          │
│       ↓                                                      │
│  5. Deploy to GitHub Pages                                  │
└─────────────────────────────────────────────────────────────┘
                          ↓
            ┌─────────────────────────────┐
            │   GitHub Pages (Public)     │
            │                             │
            │  🌐 index.html              │
            │  📊 api/models.json         │
            │  🏆 api/leaderboard.json    │
            │  📅 api/history/YYYY-MM-DD  │
            └─────────────────────────────┘
                          ↓
            ┌─────────────────────────────┐
            │  benchmarked-free-ride      │
            │  (OpenClaw Skill)           │
            │                             │
            │  Fetches scores + selects   │
            │  best model automatically   │
            └─────────────────────────────┘
```

---

## Quick Start

### Prerequisites

1. **OpenClaw CLI installed** (for local testing)
   ```bash
   npm install -g @openclaw/cli
   ```

2. **Python 3.11+**

3. **API Keys**
   - `OPENROUTER_API_KEY` - Get from [OpenRouter](https://openrouter.ai/)
   - `TAVILY_API_KEY` - Get from [Tavily](https://tavily.com/) (for web search benchmarks)

### Local Testing

```bash
# Clone repo
git clone https://github.com/sequrity-ai/benchmarked-free-ride-ci.git
cd benchmarked-free-ride-ci

# Install openclaw-benchmark submodule
git submodule update --init --recursive

# Install dependencies
pip install -r requirements.txt
pip install -e ./openclaw-benchmark

# Set environment variables
export OPENROUTER_API_KEY="your-key"
export TAVILY_API_KEY="your-key"

# Initialize OpenClaw
openclaw init

# Install required skills
clawhub install steipete/weather
clawhub install steipete/tavily

# Discover models
python3 src/discover_models.py

# Run benchmarks (just top 3 models, easy tasks only for testing)
python3 src/run_benchmarks.py \
  --discovered-models output/discovered_models.json \
  --sandbox-path ./openclaw-benchmark \
  --output-dir output/benchmarks \
  --scenarios file,weather \
  --difficulty easy \
  --max-models 3

# Generate reports
python3 src/generate_report.py \
  --benchmarks-dir output/benchmarks \
  --output-dir docs

# View results
open docs/index.html
```

---

## GitHub Setup

### 1. Create Repository

```bash
# Create a new GitHub repository named: benchmarked-free-ride-ci
gh repo create benchmarked-free-ride-ci --public
```

### 2. Configure Secrets

Go to **Settings → Secrets and variables → Actions** and add:

- `OPENROUTER_API_KEY` - Your OpenRouter API key
- `TAVILY_API_KEY` - Your Tavily API key

### 3. Enable GitHub Pages

Go to **Settings → Pages**:
- Source: Deploy from a branch
- Branch: `gh-pages` / `/ (root)`

### 4. Initialize openclaw-benchmark submodule

The repository uses openclaw-benchmark as a git submodule:

```bash
# Already configured - just initialize it
git submodule update --init --recursive

# Or if setting up from scratch
git submodule add https://github.com/sequrity-ai/openclaw-benchmark.git openclaw-benchmark
```

### 5. Push and Run

```bash
git push origin main

# Trigger manual run to test
gh workflow run daily-benchmark.yml
```

---

## How It Works

### 1. Model Discovery (`src/discover_models.py`)

Queries OpenRouter API for all models, filters for:
- **Free pricing** (`pricing.prompt == 0` or `:free` suffix)
- **Text-capable** (excludes vision, audio, embedding models)
- **Minimum context** (≥4K tokens)

Scores models using **weighted criteria** (same as FreeRide):
- Context length (40%)
- Capabilities (30%)
- Recency (20%)
- Provider trust (10%)

Selects top 10 models for benchmarking.

### 2. Benchmark Execution (`src/run_benchmarks.py`)

For each model:
1. Configures OpenClaw to use that model
2. Runs openclaw-benchmark benchmarks in **single-turn mode**
   - No AI agent needed (no OpenAI API cost)
   - Direct prompts to bot, immediate validation
3. Collects: accuracy, latency, token usage

**Default scenarios:** `file`, `weather`, `web` (fast, no external account setup)

**Default difficulty:** `easy` (3 tasks per scenario = 9 tasks total per model)

### 3. Report Generation (`src/generate_report.py`)

Aggregates all benchmark results and generates:

**Composite Score (0-100):**
- Accuracy: 70% weight
- Speed/latency: 20% weight (lower is better)
- Token efficiency: 10% weight (fewer output tokens is better)

**Outputs:**
- `docs/index.html` - Public leaderboard UI
- `docs/api/models.json` - All model stats
- `docs/api/leaderboard.json` - Ranked by composite score
- `docs/api/history/YYYY-MM-DD.json` - Daily snapshot

### 4. GitHub Pages Deployment

Workflow automatically deploys `docs/` to `gh-pages` branch.

**Live URL:** `https://YOUR_USERNAME.github.io/benchmarked-free-ride-ci/`

---

## API Endpoints

Once deployed, these JSON endpoints are publicly accessible:

### GET `/api/models.json`

List all benchmarked models with detailed stats.

```json
{
  "generated_at": "2026-03-02T10:30:00Z",
  "total_models": 10,
  "models": [
    {
      "model_id": "google/gemini-2.0-flash-exp:free",
      "quality_score": 0.82,
      "context_length": 1048576,
      "benchmarked_at": "2026-03-02T08:15:30Z",
      "total_tasks": 9,
      "passed_tasks": 8,
      "accuracy_percent": 88.89,
      "avg_latency_seconds": 3.2,
      "total_input_tokens": 12450,
      "total_output_tokens": 3210,
      "composite_score": 85.3,
      "scenarios": [
        {
          "name": "File Manipulation",
          "tasks_passed": 3,
          "tasks_total": 3,
          "avg_accuracy": 100.0
        }
      ]
    }
  ]
}
```

### GET `/api/leaderboard.json`

Ranked list of models by composite score.

```json
{
  "generated_at": "2026-03-02T10:30:00Z",
  "total_models": 10,
  "leaderboard": [
    {
      "rank": 1,
      "model_id": "google/gemini-2.0-flash-exp:free",
      "composite_score": 85.3,
      "accuracy_percent": 88.89,
      "avg_latency_seconds": 3.2,
      "context_length": 1048576
    }
  ]
}
```

### GET `/api/history/2026-03-02.json`

Daily snapshot for historical tracking.

---

## Workflow Configuration

The workflow runs daily at 2 AM UTC and can be manually triggered with custom parameters.

### Manual Trigger Parameters

```bash
gh workflow run daily-benchmark.yml \
  -f max_models=5 \
  -f scenarios="file,weather" \
  -f difficulty="easy"
```

**Parameters:**
- `max_models` - Number of top models to test (default: 10)
- `scenarios` - Comma-separated scenarios (default: `file,weather,web`)
- `difficulty` - Task difficulty (default: `easy`)
  - `easy` - 3 tasks per scenario (fast)
  - `medium` - 6 tasks per scenario
  - `hard` - 9 tasks per scenario
  - `all` - All 9 tasks per scenario

**Scenario options:**
- `file` - File manipulation (no external deps)
- `weather` - Weather queries (needs `steipete/weather`)
- `web` - Web search (needs `steipete/tavily` + `TAVILY_API_KEY`)
- `summarize` - URL/doc summarization (needs `steipete/summarize`)
- `gmail` - Email operations (needs `gog` + Gmail OAuth setup)
- `github` - GitHub operations (needs `steipete/github` + GitHub token)

---

## Companion Skill

The **benchmarked-free-ride-skill** repository contains an OpenClaw skill that:

1. Fetches leaderboard from the published API
2. Shows top models with scores
3. Auto-configures OpenClaw to use the best free model

**Usage:**
```bash
# Install skill
clawhub install sequrity-ai/benchmarked-free-ride

# View leaderboard
benchmarked-free-ride leaderboard

# Auto-select best model
benchmarked-free-ride auto
```

See [benchmarked-free-ride-skill](https://github.com/sequrity-ai/benchmarked-free-ride-skill) for details.

---

## Troubleshooting

### Workflow fails with "OpenClaw CLI not found"

Ensure the workflow has the Node.js setup step:
```yaml
- uses: actions/setup-node@v4
  with:
    node-version: '20'
- run: npm install -g @openclaw/cli
```

### Benchmark fails: "No such file openclaw-benchmark"

Initialize the openclaw-benchmark submodule:
```bash
git submodule update --init --recursive
```

### GitHub Pages shows 404

1. Check **Settings → Pages** - ensure `gh-pages` branch is selected
2. Wait 2-3 minutes after first deployment
3. Check Actions tab for deployment errors

### Benchmarks timeout

Reduce scope:
```bash
gh workflow run daily-benchmark.yml \
  -f max_models=3 \
  -f scenarios="file" \
  -f difficulty="easy"
```

---

## Cost Analysis

### Free Tier Usage

**GitHub Actions:** 2,000 free minutes/month for public repos
- Expected usage: ~30-60 min/day = 900-1800 min/month ✅

**OpenRouter:** Free models only, no API cost ✅

**Tavily:** 1,000 free searches/month
- Usage: ~3 searches × 10 models = 30/day = 900/month ✅

**Storage:** GitHub Pages is free for public repos ✅

### Optional Paid Usage

To benchmark **all scenarios with all difficulties:**
- Enable Gmail/GitHub scenarios (requires account setup)
- Run `difficulty=all` (27 tasks/model instead of 9)
- Increase `max_models` beyond 10

---

## Development

### Adding New Scenarios

Edit `src/run_benchmarks.py` to include more scenarios from openclaw-benchmark:
```python
scenarios = ["file", "weather", "web", "summarize", "gmail", "github"]
```

Ensure required skills are installed in workflow:
```yaml
- run: clawhub install steipete/summarize
```

### Customizing Scoring

Edit `src/generate_report.py` → `calculate_composite_score()`:
```python
# Current: 70% accuracy, 20% latency, 10% tokens
accuracy_score = (avg_accuracy / 100) * 0.7
latency_score = max(0, 1 - (avg_latency / 60)) * 0.2
token_efficiency_score = max(0, 1 - (avg_output_tokens / 1000)) * 0.1
```

### Testing Locally with Docker

```bash
docker build -t benchmarked-free-ride .
docker run -e OPENROUTER_API_KEY=$OPENROUTER_API_KEY benchmarked-free-ride
```

---

## License

Part of the Sequrity project. See parent repository for license details.

---

## Related Projects

- [FreeRide](https://github.com/openclaw/skills/tree/main/skills/shaivpidadi/free-ride) - Original inspiration, auto-configures free models
- [OpenClaw](https://github.com/openclaw/openclaw) - AI agent framework
- [openclaw-benchmark](https://github.com/sequrity-ai/openclaw-benchmark) - Benchmark test suite
- [benchmarked-free-ride-skill](https://github.com/sequrity-ai/benchmarked-free-ride-skill) - OpenClaw skill to fetch and auto-configure best models
