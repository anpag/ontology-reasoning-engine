# Enterprise Scale Ontology Reasoning Engine

**Disclaimer:** This is a personal development project. It is not an official product of Google, nor is it endorsed by or affiliated with Google in any way.

A highly scalable, memory-safe microservice designed to ingest massive Semantic Web Ontologies (OWL, Turtle, JSON-LD) and apply rigorous Description Logic materialization via Forward Chaining.

## Architecture Overview

This microservice utilizes a decoupled **Python/Rust Hybrid Architecture** to guarantee absolute memory safety and blistering speed at scale (tested on 16.4+ million triples).

1. **API Layer (Python 3.11 / FastAPI)**: 
   Acts as a stateless, non-blocking HTTP router. It asynchronously handles file uploads and coordinates the backend processes to prevent HTTP timeouts.
2. **Parsing Layer (Rust Oxigraph)**: 
   To prevent memory bottlenecks during gigabyte-scale XML parsing, the engine statically embeds the native Rust `oxrdfxml` and `oxttl` micro-libraries, achieving native C++ deserialization speeds.
3. **Reasoning Engine (Native Rust)**: 
   A custom-compiled Rust binary handles the mathematical Description Logic materialization. Leveraging `petgraph`'s `DiGraph` and `FixedBitSet` Breadth-First-Search (BFS) algorithms, it calculates the transitive closures of `rdfs:subClassOf`, `rdfs:domain`, `rdfs:range`, and `owl:equivalentClass` safely and instantly. Output is directly serialized to `.nt` (N-Triples).

## Performance Benchmarks
*Tested on an `n2-standard-4` equivalent Linux instance.*

| Ontology | Format | Initial Triples | Inferred Triples | Total Processing Time | Memory Safety |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **ChEBI** | XML | 9,521,942 | 6,952,622 | 5m 31.6s | Guaranteed (Rust) |
| **QUDT** | Turtle | 42,435 | 0 | 0.12s | Guaranteed (Rust) |

## Quick Start (Local Development)

### Prerequisites
* `cargo` (Rust Toolchain v1.80+)
* `python3.11`
* `docker`

### 1. Compile the Rust Engine
```bash
cd rust_engine
cargo build --release
```

### 2. Start the API Server
```bash
pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 8080 --reload
```

## Production Deployment

This repository utilizes a **Multi-Stage Docker Build**. 
* **Stage 1** compiles the Rust binary natively, completely isolating all build dependencies (Cargo, rustc).
* **Stage 2** constructs a minimal `python:3.11-slim` runtime environment, injecting *only* the finalized executable alongside the FastAPI routers.

```bash
# Build the highly optimized Docker Image
docker build -t your-registry/ontology-reasoner .

# Push to your Container Registry
docker push your-registry/ontology-reasoner

# Deploy to your managed container platform
gcloud run deploy ontology-reasoner \
  --image your-registry/ontology-reasoner \
  --platform managed \
  --memory 8Gi \
  --cpu 4 \
  --allow-unauthenticated
```

## API Documentation

### `POST /ingest`
Ingests an ontology and processes it asynchronously.

**Form Data:**
* `file`: The raw ontology file (e.g. `.owl` or `.ttl`).
* `format`: The parsing format (must be `"xml"` or `"turtle"`).

**Response (200 OK):**
```json
{
  "status": "accepted",
  "message": "Ontology received. Reasoning started in the background.",
  "job_id": "tmp12345.xml"
}
```

### `GET /result/{job_id}`
Retrieves the materialized N-Triples output graph.

**Response:**
* **200 OK**: Streams the `_reasoned.nt` N-Triples file.
* **404 Not Found**: If the processing is still ongoing or the `job_id` is invalid.
