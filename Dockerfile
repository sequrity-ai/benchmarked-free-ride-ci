# Dockerfile for OpenClaw Benchmark Runner
# Use Python 3.13 as base, then install Node.js
FROM python:3.13-slim-bookworm

# Install build tools, Node.js 22, and other dependencies
RUN apt-get update && \
    apt-get install -y ca-certificates curl gnupg git build-essential && \
    mkdir -p /etc/apt/keyrings && \
    curl -fsSL https://deb.nodesource.com/gpgkey/nodesource-repo.gpg.key | gpg --dearmor -o /etc/apt/keyrings/nodesource.gpg && \
    echo "deb [signed-by=/etc/apt/keyrings/nodesource.gpg] https://deb.nodesource.com/node_22.x nodistro main" | tee /etc/apt/sources.list.d/nodesource.list && \
    apt-get update && \
    apt-get install -y nodejs && \
    rm -rf /var/lib/apt/lists/* && \
    node --version && npm --version

# Verify Python version
RUN python --version

# Create working directory
WORKDIR /app

# Install OpenClaw CLI using official install script
# Skip interactive setup in Docker by setting CI=true
ENV CI=true
RUN curl -fsSL https://openclaw.ai/install.sh | bash || true
# Add OpenClaw to PATH permanently
ENV PATH="/root/.openclaw/bin:${PATH}"
RUN openclaw --version

# Initialize OpenClaw (creates ~/.openclaw directory)
RUN openclaw init --non-interactive 2>&1 || echo "OpenClaw init completed (may need API keys at runtime)"

# Install required skills (may fail without auth, will configure at runtime)
RUN openclaw skill install steipete/weather 2>&1 || echo "Weather skill will be configured at runtime" && \
    openclaw skill install steipete/tavily 2>&1 || echo "Tavily skill will be configured at runtime" && \
    openclaw skill install steipete/summarize 2>&1 || echo "Summarize skill will be configured at runtime"

# Copy Python requirements first for better caching
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir --break-system-packages --upgrade pip && \
    python3 -m pip install --no-cache-dir --break-system-packages -r requirements.txt

# Copy source code
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY openclaw-benchmark/ ./openclaw-benchmark/
COPY agentdojo/ ./agentdojo/

# Install openclaw-benchmark dependencies
WORKDIR /app/openclaw-benchmark
RUN python3 -m pip install --no-cache-dir --break-system-packages -e .

# Install AgentDojo dependencies
WORKDIR /app/agentdojo
RUN python3 -m pip install --no-cache-dir --break-system-packages -e .

# Verify installation
RUN python3 -c "import sys; print(f'Python version: {sys.version}')" && \
    openclaw --version && \
    python3 -c "import cli; print('openclaw-benchmark CLI imported successfully')"

WORKDIR /app

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV LOCAL_MODE=true
ENV PATH="/usr/local/bin:$PATH"

# Default command
CMD ["python3", "src/run_benchmarks.py"]
