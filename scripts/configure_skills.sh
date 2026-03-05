#!/bin/bash
# Configure OpenClaw skills with API keys at runtime
# This script runs inside the Docker container before benchmarks start

set -e

CONFIG_FILE="$HOME/.openclaw/openclaw.json"

echo "Configuring OpenClaw skills..."

# Check if config file exists
if [ ! -f "$CONFIG_FILE" ]; then
    echo "Error: OpenClaw config file not found at $CONFIG_FILE"
    exit 1
fi

# Configure Tavily skill if TAVILY_API_KEY is set
if [ -n "$TAVILY_API_KEY" ]; then
    echo "Configuring Tavily skill with API key..."

    # Use Python to update the JSON config
    python3 << EOF
import json
import os

config_file = os.path.expanduser("$CONFIG_FILE")

# Load existing config
with open(config_file, 'r') as f:
    config = json.load(f)

# Ensure skills.entries exists
if 'skills' not in config:
    config['skills'] = {}
if 'entries' not in config['skills']:
    config['skills']['entries'] = {}

# Configure tavily-search skill
if 'steipete/tavily' not in config['skills']['entries']:
    config['skills']['entries']['steipete/tavily'] = {}
if 'env' not in config['skills']['entries']['steipete/tavily']:
    config['skills']['entries']['steipete/tavily']['env'] = {}

config['skills']['entries']['steipete/tavily']['env']['TAVILY_API_KEY'] = os.environ.get('TAVILY_API_KEY', '')

# Save updated config
with open(config_file, 'w') as f:
    json.dump(config, f, indent=2)

print(f"✓ Tavily skill configured")
EOF
else
    echo "⚠ TAVILY_API_KEY not set - web search scenarios will be skipped"
fi

echo "✓ Skill configuration complete"
