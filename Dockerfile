# Dockerfile for OpenClaw Benchmark Runner
FROM node:20-bookworm-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    python3.11 \
    python3-pip \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create working directory
WORKDIR /app

# Install OpenClaw CLI globally
RUN npm install -g @openclaw/cli

# Initialize OpenClaw (creates ~/.openclaw directory)
RUN openclaw init --non-interactive || true

# Copy Python requirements first for better caching
COPY requirements.txt .
RUN pip3 install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY openclaw-benchmark/ ./openclaw-benchmark/

# Install openclaw-benchmark dependencies
WORKDIR /app/openclaw-benchmark
RUN pip3 install --no-cache-dir -e .

WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV LOCAL_MODE=true

# Default command
CMD ["python3", "src/run_benchmarks.py"]
