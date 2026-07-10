#!/bin/bash
set -e

# Navigate to rust engine directory
cd "$(dirname "$0")/../rust_engine"

echo "Checking for Cargo..."
if ! command -v cargo &> /dev/null
then
    echo "Cargo not found. Installing..."
    sudo apt-get update && sudo apt-get install -y cargo
fi

echo "Building Rust Reasoner (Release mode)..."
cargo build --release

echo "Build complete. Executing tests."
cd ..

CHEBI_PATH="../tests/chebi.owl"
QUDT_PATH="../tests/qudt_unit.ttl"

# Test 1: ChEBI
if [ -f "$CHEBI_PATH" ]; then
    echo "========================================"
    echo "Testing ChEBI (XML Format)"
    echo "========================================"
    time ./rust_engine/target/release/custom_reasoner_rust xml "$CHEBI_PATH" /tmp/chebi_out.nt
else
    echo "ChEBI file not found at $CHEBI_PATH"
fi

# Test 2: QUDT
if [ -f "$QUDT_PATH" ]; then
    echo "========================================"
    echo "Testing QUDT (Turtle Format)"
    echo "========================================"
    time ./rust_engine/target/release/custom_reasoner_rust turtle "$QUDT_PATH" /tmp/qudt_out.nt
else
    echo "QUDT file not found at $QUDT_PATH"
fi
