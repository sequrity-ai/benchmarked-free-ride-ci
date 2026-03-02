# Submodule Setup Instructions

This repository uses `openclaw-benchmark` as a git submodule.

## Quick Setup

```bash
cd benchmarked-free-ride-ci

# Add the submodule
git submodule add https://github.com/sequrity-ai/openclaw-benchmark.git openclaw-benchmark

# Commit and push
git add .
git commit -m "Add openclaw-benchmark as submodule"
git push
```

## What Was Updated

All references to the benchmark suite have been updated from `opencalw-sandbox` to `openclaw-benchmark`:

✅ `.github/workflows/daily-benchmark.yml` - Workflow now uses submodule
✅ `src/run_benchmarks.py` - Default path updated
✅ `Dockerfile` - Build process updated
✅ `requirements.txt` - Comment updated

## GitHub Actions Behavior

The workflow automatically checks out submodules:

```yaml
- uses: actions/checkout@v4
  with:
    submodules: 'recursive'
```

This means the `openclaw-benchmark` directory will be available during CI runs.

## Local Development

If you clone this repo fresh, initialize the submodule:

```bash
git clone https://github.com/YOUR_USERNAME/benchmarked-free-ride-ci.git
cd benchmarked-free-ride-ci

# Initialize submodule
git submodule init
git submodule update

# Or in one command
git submodule update --init --recursive
```

## Updating the Submodule

To pull latest changes from openclaw-benchmark:

```bash
cd openclaw-benchmark
git pull origin main
cd ..

# Commit the submodule update
git add openclaw-benchmark
git commit -m "Update openclaw-benchmark to latest"
git push
```

## Why Submodule?

Benefits:
- ✅ No code duplication
- ✅ Always uses the public openclaw-benchmark repo
- ✅ Can pin to specific commits if needed
- ✅ Easier to keep in sync with upstream
- ✅ CI automatically gets the benchmark suite
