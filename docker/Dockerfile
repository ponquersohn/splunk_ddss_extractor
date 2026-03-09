FROM python:3.12-slim AS builder

WORKDIR /app

# Install Rust toolchain and build dependencies
RUN apt-get update && apt-get install -y \
    curl \
    gcc \
    g++ \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.cargo/bin:${PATH}"

# Install maturin
RUN pip install --no-cache-dir maturin

# Copy source
COPY pyproject.toml README.md ./
COPY src/ src/
COPY rust/ rust/

# Build the wheel with native extension
RUN maturin build --release --find-interpreter \
    && pip install --no-cache-dir rust/target/wheels/splunk_ddss_extractor-*.whl

# --- Runtime stage ---
FROM python:3.12-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin/splunk-extract /usr/local/bin/splunk-extract

# Install runtime dependencies (zstandard needs the shared lib)
RUN pip install --no-cache-dir zstandard orjson

# Create non-root user
RUN useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

USER appuser

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import sys; sys.exit(0)"

CMD ["splunk-extract", "--help"]
