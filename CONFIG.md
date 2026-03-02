# Benchmark Configuration

This document explains the benchmark configuration and how to customize it.

## Default Configuration (Optimized for Free Tier)

The workflow is configured to stay well within GitHub Actions' free tier of 2,000 minutes/month.

### Current Settings

```yaml
Schedule: Weekly (Sundays at 2 AM UTC)
Models: Top 5 free models
Scenarios: file, weather, web
Difficulty: easy (3 tasks per scenario)
Mode: single-turn (no AI agent, no OpenAI API cost)
```

### What Gets Benchmarked

**Per model:**
- 3 scenarios × 3 tasks = **9 tasks total**

**Total per run:**
- 5 models × 9 tasks = **45 tasks**

**Estimated runtime:**
- ~5-10 minutes per run
- 4 runs/month (weekly) = **20-40 minutes/month**
- Well within free tier ✅

---

## Task Difficulty Levels

Each scenario has 9 total tasks split across 3 difficulty levels:

### Easy (default)
- **3 tasks per scenario**
- Simple, straightforward operations
- Fast execution (~1-2 min/model/scenario)
- Best for daily/weekly monitoring

### Medium
- **3 additional tasks** (6 total with easy)
- More complex operations
- Moderate execution time (~2-4 min/model/scenario)

### Hard
- **3 additional tasks** (9 total)
- Multi-step operations
- Longer execution time (~3-5 min/model/scenario)

### All
- **All 9 tasks per scenario**
- Complete coverage
- Longest execution time (~6-10 min/model/scenario)

---

## Scenario Overview

### Included by Default

| Scenario | Tasks | Description | Dependencies |
|----------|-------|-------------|--------------|
| **file** | 3 easy | File manipulation, JSON→CSV, data extraction | None (built-in) |
| **weather** | 3 easy | Current weather, forecasts, comparisons | `steipete/weather` |
| **web** | 3 easy | Web search, fact retrieval | `steipete/tavily` + `TAVILY_API_KEY` |

### Available but Not Default

| Scenario | Tasks | Description | Dependencies |
|----------|-------|-------------|--------------|
| **summarize** | 3 easy | URL/YouTube summaries | `steipete/summarize` |
| **gmail** | 3 easy | Email search, send, read | `gog` + Gmail OAuth |
| **github** | 3 easy | Create issues, list PRs | `steipete/github` + `GITHUB_TOKEN` |
| **compound** | 3 easy | Multi-skill chains | Multiple skills |

---

## Cost Analysis by Configuration

### Recommended: Current Default
```yaml
Schedule: Weekly
Models: 5
Difficulty: easy
Scenarios: file,weather,web
```
- **45 tasks/run**
- **~10 min/run**
- **40 min/month** (4 runs)
- Cost: **FREE** ✅

### Moderate: Daily Easy
```yaml
Schedule: Daily
Models: 5
Difficulty: easy
Scenarios: file,weather,web
```
- **45 tasks/run**
- **~10 min/run**
- **300 min/month** (30 runs)
- Cost: **FREE** ✅

### Aggressive: Daily All Scenarios Easy
```yaml
Schedule: Daily
Models: 5
Difficulty: easy
Scenarios: file,weather,web,summarize,gmail,github
```
- **90 tasks/run** (6 scenarios)
- **~20 min/run**
- **600 min/month**
- Cost: **FREE** ✅

### Maximum: Daily All Tasks
```yaml
Schedule: Daily
Models: 10
Difficulty: all
Scenarios: file,weather,web,summarize,gmail,github
```
- **540 tasks/run** (10 models × 6 scenarios × 9 tasks)
- **~120 min/run**
- **3,600 min/month**
- Cost: **EXCEEDS FREE TIER** ❌
- Solution: Use self-hosted runner or reduce scope

---

## How to Customize

### Option 1: Modify Workflow File

Edit `.github/workflows/daily-benchmark.yml`:

```yaml
on:
  schedule:
    # Change schedule (examples):
    - cron: '0 2 * * *'      # Daily at 2 AM
    - cron: '0 2 * * 0,3'    # Twice weekly (Sun, Wed)
    - cron: '0 */6 * * *'    # Every 6 hours

  workflow_dispatch:
    inputs:
      max_models:
        default: '10'         # Change default model count
      scenarios:
        default: 'file,weather,web,summarize'  # Add/remove scenarios
      difficulty:
        default: 'all'        # Change to medium, hard, or all
```

### Option 2: Manual Trigger with Custom Parameters

Trigger via GitHub Actions UI:
1. Go to **Actions → Daily Model Benchmarks**
2. Click **Run workflow**
3. Set custom parameters:
   - `max_models`: 3
   - `scenarios`: file,weather
   - `difficulty`: easy

Or via CLI:
```bash
gh workflow run daily-benchmark.yml \
  -f max_models=3 \
  -f scenarios="file,weather" \
  -f difficulty="easy"
```

### Option 3: Environment-Specific Configs

Create different workflow files for different needs:

**`.github/workflows/quick-benchmark.yml`** (for testing):
```yaml
on:
  workflow_dispatch:
defaults:
  max_models: 1
  scenarios: file
  difficulty: easy
```

**`.github/workflows/full-benchmark.yml`** (for comprehensive runs):
```yaml
on:
  workflow_dispatch:
defaults:
  max_models: 10
  scenarios: file,weather,web,summarize,gmail,github
  difficulty: all
```

---

## Understanding the Easy Subset

### What Easy Tasks Test

The easy tasks cover fundamental capabilities:

#### File Scenario (Easy)
1. **File Organization** - Create directories and files
2. **File Modification** - Edit existing files
3. **File Consolidation** - Merge data into CSV

#### Weather Scenario (Easy)
1. **Current Weather** - Get current conditions for a city
2. **Weather Forecast** - Get 3-day forecast
3. **Weather Comparison** - Compare two cities

#### Web Scenario (Easy)
1. **Factual Search** - Find basic facts
2. **Comparison Research** - Compare two concepts
3. **Current Events** - Find recent developments

### Why Easy Is Sufficient

✅ **Covers core functionality** - Tests basic model capabilities
✅ **Fast execution** - Quick feedback on model quality
✅ **Cost-effective** - Minimal CI minutes used
✅ **Reliable** - Less prone to flakiness than complex tasks
✅ **Differentiates models** - Easy tasks still show performance differences

The composite score (accuracy + latency + tokens) from easy tasks is **highly correlated** with overall model quality.

---

## Scaling Up

If you want more comprehensive benchmarks:

### Step 1: Add More Scenarios
```yaml
scenarios: 'file,weather,web,summarize'  # Add summarize
```

Ensure required skill is installed:
```yaml
- run: clawhub install steipete/summarize
```

### Step 2: Increase Difficulty
```yaml
difficulty: 'medium'  # or 'all'
```

### Step 3: Increase Model Count
```yaml
max_models: '10'  # Test all top 10
```

### Step 4: Monitor Usage
```bash
# Check GitHub Actions usage
gh api /repos/OWNER/REPO/actions/billing/usage
```

### Step 5: Consider Self-Hosted Runner

For unlimited runs:
```yaml
runs-on: self-hosted  # Instead of ubuntu-latest
```

---

## Recommendations

### For Development/Testing
```yaml
max_models: 1
scenarios: file
difficulty: easy
```
**Purpose:** Quick validation (~2 min)

### For Production Monitoring
```yaml
max_models: 5
scenarios: file,weather,web
difficulty: easy
Schedule: Weekly
```
**Purpose:** Regular quality tracking (current default)

### For Comprehensive Analysis
```yaml
max_models: 10
scenarios: file,weather,web,summarize
difficulty: all
Schedule: Monthly or self-hosted
```
**Purpose:** Deep model evaluation

---

## FAQ

**Q: Can I run just one scenario?**
A: Yes! Set `scenarios: 'file'` for just file manipulation tests.

**Q: How do I test just the top model?**
A: Set `max_models: '1'`

**Q: What if I want to benchmark paid models too?**
A: Modify `src/discover_models.py` to remove the free-only filter.

**Q: Can I run this locally?**
A: Yes! See `README.md` for local testing instructions.

**Q: How do I add custom tasks?**
A: Edit the scenario files in `opencalw-sandbox/benchmarks/scenarios/`.

---

## Summary

✅ **Default configuration runs ONLY easy tasks**
✅ **5 models × 3 scenarios × 3 tasks = 45 total tasks**
✅ **Weekly schedule = ~40 min/month (well within free tier)**
✅ **Easy to customize via workflow parameters**
✅ **Scales from 1 model to 10+ models**

The easy subset provides excellent model quality signals while keeping costs minimal.
