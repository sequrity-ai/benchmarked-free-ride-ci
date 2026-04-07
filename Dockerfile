# Dockerfile for OpenClaw Benchmark Runner
# Runs openclawbench with --backend=daytona (no local openclaw needed)
FROM python:3.13-slim-bookworm

# Install build tools and git
RUN apt-get update && \
    apt-get install -y ca-certificates curl gnupg git build-essential && \
    rm -rf /var/lib/apt/lists/*

# Install uv (used by openclawbench)
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.local/bin:${PATH}"
RUN uv --version

# Verify Python version
RUN python --version

# Create working directory
WORKDIR /app

# Copy Python requirements first for better caching
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir --break-system-packages --upgrade pip && \
    python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY openclawbench/ ./openclawbench/
COPY agentdojo/ ./agentdojo/
COPY cracker/ ./cracker/

# Install openclawbench dependencies (for imports by run_benchmarks.py)
WORKDIR /app/openclawbench
RUN uv sync

# Install AgentDojo dependencies
WORKDIR /app/agentdojo
RUN python3 -m pip install --no-cache-dir --break-system-packages -e .

# Install Cracker and its workspace member into system Python via uv
WORKDIR /app/cracker
RUN uv pip install --system -e ./openclawbench && \
    uv pip install --system -e .

WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["python3", "src/run_benchmarks.py"]
