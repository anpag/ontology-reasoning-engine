# Stage 1: Build the Rust Engine
FROM rust:1.80-slim as builder

WORKDIR /usr/src/app

# Copy the Rust engine source code
COPY rust_engine ./rust_engine

# Compile the release binary natively for Linux x86_64
WORKDIR /usr/src/app/rust_engine
RUN cargo build --release

# Stage 2: Construct the lightweight Python Runtime
FROM python:3.11-slim

WORKDIR /app

# Install minimal system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the pre-compiled Rust binary from the builder stage
# This ensures zero Rust compilation dependencies exist in production
COPY --from=builder /usr/src/app/rust_engine/target/release/custom_reasoner_rust /app/rust_engine/target/release/custom_reasoner_rust
RUN chmod +x /app/rust_engine/target/release/custom_reasoner_rust

# Copy the Python API and Core Logic
COPY api/ ./api/
COPY core/ ./core/

# Expose standard Cloud Run port
EXPOSE 8080

# Execute the FastAPI server
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8080"]
