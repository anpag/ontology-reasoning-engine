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

## Data Modeling & Ontology Standards

This reasoning engine processes standards-compliant RDF/OWL graphs, heavily focusing on scientific interoperability using W3C and industry ontologies:

*   **Allotrope (AFO) & EMMO**: Used for parsing laboratory analytics and material science semantics.
*   **ChEBI**: Deployed for biochemical entity classifications.
*   **QUDT (Quantities, Units, Dimensions, and Types)**: 
    *   To allow algorithms to mathematically analyze heterogeneous global sensor data (e.g., mixing Celsius, Fahrenheit, and Kelvin), the system natively supports the QUDT structural schema. 
    *   Measurements are never stored as flat strings (e.g., `"100 °C"`). Instead, they are structured as strictly typed `QuantityValue` subgraphs containing numeric values and pointers to canonical `Unit` nodes. 
    *   This embeds the exact `conversionMultiplier` and `conversionOffset` math directly into the graph edges, enabling downstream databases like BigQuery to perform automated mathematical conversions via SPARQL without custom middleware.

## Motivation & Technical Justification

Standard semantic web tooling is often designed for desktop-scale ontologies and fails drastically under Enterprise-scale loads. We undertook a rigorous benchmarking journey to determine the optimal architecture for this microservice:

1. **The Python Bottleneck (`rdflib` / `owlready2`)**: 
   Initial tests utilizing standard Python libraries to parse the 1.5GB ChEBI XML ontology resulted in massive memory bloat. The parsing phase alone took **7.5 minutes**, creating an unacceptable bottleneck for a stateless HTTP API.
2. **The C++ Risk (`raptor2`)**: 
   We subsequently wrote a custom C++ parsing engine utilizing `librdf`/`raptor2`. While this successfully reduced XML parsing time to **21 seconds**, managing raw pointers for a graph of 16.4 million triples in a highly concurrent microservice environment posed an unacceptable risk of segmentation faults and memory leaks.
3. **The Native Rust Solution**: 
   By embedding the micro-crates `oxrdfxml` and `oxttl` into a purely Native Rust binary, we achieved the blistering speed of C++ deserialization while benefiting from Rust's strict compiler-guaranteed memory safety. 

By offloading the mathematical DL materialization to `petgraph`, this microservice parses, infers, and serializes millions of triples in minutes without suffering from string duplication or heap fragmentation.

## Performance Benchmarks & Engine Comparisons
*Tested on an `n2-standard-4` equivalent Linux instance.*

| Ontology | Engine | Format | Initial Triples | Inferred Triples | Total Processing Time |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **NCIT (NCI Thesaurus)** | HermiT (Java/JVM)* | XML | 10,769,587 | 2,955,662 | 10m 07.4s (607.4s) |
| **NCIT (NCI Thesaurus)** | Native Rust | XML | 10,769,587 | 2,955,662 | **2m 55.8s** |
| **ChEBI** | Native Rust | XML | 9,521,942 | 6,952,622 | **5m 31.6s** |
| **GO (Gene Ontology)** | HermiT (Java/JVM) | XML | 1,444,892 | 926,782 | 1m 38.9s (98.9s) |
| **GO (Gene Ontology)** | Native Rust | XML | 1,444,892 | 926,782 | **42.5s** |
| **QUDT** | Native Rust | Turtle | 42,435 | 0 | **0.12s** |

*\*Note: HermiT required 32GB of allocated JVM Heap Space to complete the NCIT benchmark without throwing an `OutOfMemoryError`.*

### What are "Inferred Triples"?
In a semantic knowledge graph, not all relationships are explicitly stated. If an ontology states that *Aspirin* is a *Painkiller*, and a *Painkiller* is a *Drug*, the graph implicitly knows that *Aspirin* is a *Drug*. **Inferred Triples** are the new, mathematically deduced relationships our engine generates (via Transitive Closure rules like `rdfs:subClassOf`) that were not present in the original file. Materializing these inferred triples ahead of time means BigQuery can execute standard queries instantly without needing to calculate hierarchies on the fly.

### Comparison with Standard Reasoners
Most standard semantic reasoners (e.g., **HermiT**, **Pellet**) are built on the Java Virtual Machine (JVM). 
*   **JVM Overhead:** When processing extreme Google-scale ontologies (10M+ triples), JVM-based reasoners typically encounter catastrophic `OutOfMemoryError` (OOM) exceptions unless provisioned with massive, costly RAM allocations. Even when they succeed, Java's garbage collection pauses severely bottleneck processing times, often taking hours.
*   **ELK Reasoner:** While **ELK** is highly optimized for OWL EL profiles, our custom Rust implementation focuses on direct RDFS+ DL materialization. By leveraging `petgraph`'s bitsets and zero-cost abstractions, we bypass JVM bloat entirely, achieving bare-metal execution speeds while calculating millions of inferences in under 6 minutes.

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
