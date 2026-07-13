# GEB: Graph Entailment Backplane

*An homage to Douglas Hofstadter's "Gödel, Escher, Bach: An Eternal Golden Braid"*

Growing up, I was a massive fan of Douglas Hofstadter's work, particularly his exploration of formal logic, recursion, and self-referential systems in *Gödel, Escher, Bach* and *I Am a Strange Loop*. In Semantic Web engineering, Description Logic (DL) materialization operates on these exact same principles: the engine recursively forward-chains through ontology axioms, constantly feeding its own outputs back into itself until it reaches a logical fixpoint—a true "Strange Loop." This project is named **GEB (Graph Entailment Backplane)** as a backronym to honor the profound impact Hofstadter's writings had on my understanding of recursive logical systems.

A highly scalable, memory-safe microservice designed to ingest massive Semantic Web Ontologies (OWL, Turtle, JSON-LD) and apply rigorous Description Logic materialization via Forward Chaining. It natively supports **OWL 2 RL/EL Profiles**, **eXtreme Design (XD) Modularity**, and **BigQuery Labeled Property Graph (LPG)** projections.

## Architecture Overview

This microservice utilizes a decoupled **Python/Rust Hybrid Architecture** to guarantee absolute memory safety and blistering speed at scale (tested on 16.4+ million triples).

1. **API Layer (Python 3.11 / FastAPI)**: 
   Acts as a stateless, non-blocking HTTP router. It asynchronously handles file uploads and coordinates the backend processes to prevent HTTP timeouts.
2. **Parsing Layer (Rust Oxigraph & Reqwest)**: 
   To prevent memory bottlenecks during gigabyte-scale XML parsing, the engine statically embeds the native Rust `oxrdfxml` and `oxttl` micro-libraries, achieving native C++ deserialization speeds. It uses `reqwest` to recursively resolve HTTP-based `owl:imports`.
3. **Reasoning Engine (Native Rust)**: 
   A custom-compiled Rust binary handles the mathematical Description Logic materialization. Leveraging `petgraph`'s `DiGraph` and `FixedBitSet` Breadth-First-Search (BFS) algorithms, it calculates the transitive closures of `rdfs:subClassOf`, `rdfs:domain`, `rdfs:range`, `owl:equivalentClass`, and custom `owl:TransitiveProperty` logic safely and instantly.

## Advanced W3C Engineering Features

### 1. OWL 2 RL / EL Inference Rules
Unlike basic RDFS inferencers, our Rust engine supports deep logical constraints typically reserved for heavy Java/JVM reasoners (like HermiT or Pellet).
*   **`owl:SymmetricProperty`**: (e.g., `skos:exactMatch` or `foaf:knows`). If `A knows B`, the engine automatically infers `B knows A`.
*   **`owl:inverseOf`**: (e.g., `skos:broader` and `skos:narrower`). If `ConceptA broader ConceptB`, the engine infers `ConceptB narrower ConceptA`.
*   **`owl:TransitiveProperty`**: Beyond the standard `subClassOf`, the engine dynamically discovers any custom transitive property (like `skos:broaderTransitive` or `partOf`) and compiles dedicated in-memory graphs to resolve transitive closures in milliseconds.

### 2. eXtreme Design (XD) & Modular Ontology Merging
Monolithic ontologies are a relic of the past. Modern ontology engineering emphasizes modularity. 
When parsing a file, our engine actively detects `owl:imports` triples. It queues the target URIs and natively fires HTTP GET requests to resolve, download, and seamlessly merge the imported dependencies (e.g., FOAF or SKOS specs) into the unified graph memory space prior to inference.

### 3. BigQuery Labeled Property Graph (LPG) Generation
**The Problem**: The W3C RDF standard strictly forbids edges from having properties. If a sensor records a temperature of 100°C with 99% confidence, RDF forces you to create an intermediate "Observation" or "Statement" node (Reification). This destroys SQL performance by forcing complex, multi-hop joins.
**The Solution**: Our engine bridges the gap between Academic RDF and Enterprise Data Warehousing. When executing in `lpg` mode, the engine hunts for Reification nodes (`rdf:Statement`). It mathematically collapses these intermediate structures and maps them directly into flat, high-performance BigQuery Labeled Property Graphs (`.jsonl`), embedding all metadata as JSON key-value properties directly on the edge!

## CLI Usage Modes

The core Rust engine is executed via the CLI. It requires you to explicitly select an execution mode based on your architectural needs.

### Mode 1: Strict W3C Compliance (`w3c`)
Best for traditional academic semantic web pipelines. Only generates standard N-Triples.
```bash
./target/release/geb_engine turtle w3c my_ontology.ttl output_w3c
# Result: Generates output_w3c.nt containing pure RDF triples.
```

### Mode 2: BigQuery Property Graph (`lpg`)
Best for high-performance Google Cloud analytics and OBDA (Ontology-Based Data Access).
```bash
./target/release/geb_engine turtle lpg my_ontology.ttl output_lpg
# Result: Generates output_lpg.nt AND output_lpg_edges.jsonl
```

**Example JSON-L Output (`output_lpg_edges.jsonl`):**
```json
{
  "src": "<http://example.org/ExperimentA>",
  "edge_label": "<http://example.org/hasTemperature>",
  "dst": "\"100\"^^<http://www.w3.org/2001/XMLSchema#integer>",
  "properties": {
    "http://example.org/unit": "\"Celsius\"",
    "http://example.org/confidence": "\"0.99\"^^<http://www.w3.org/2001/XMLSchema#float>"
  }
}
```

## Performance Benchmarks & Engine Comparisons
*Tested on an `n2-standard-4` equivalent Linux instance.*

| Ontology | Engine | Format | Initial Triples | Inferred Triples | Total Processing Time |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **NCIT (NCI Thesaurus)** | HermiT (Java/JVM)* | XML | 10,769,587 | 2,955,662 | 10m 07.4s (607.4s) |
| **NCIT (NCI Thesaurus)** | Native Rust | XML | 10,769,587 | 2,955,662 | **2m 55.8s** |
| **ChEBI** | Native Rust | XML | 9,521,942 | 6,952,622 | **5m 31.6s** |
| **GO (Gene Ontology)** | HermiT (Java/JVM) | XML | 1,444,892 | 926,782 | 1m 38.9s (98.9s) |
| **GO (Gene Ontology)** | Native Rust | XML | 1,444,892 | 926,782 | **42.5s** |
| **FOAF + SKOS (Modular)**| Native Rust (`lpg`) | Turtle | 634 | 30 | **< 1.0s** |

*\*Note: HermiT required 32GB of allocated JVM Heap Space to complete the NCIT benchmark without throwing an `OutOfMemoryError`.*

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
docker build -t your-registry/geb-engine .

# Push to your Container Registry
docker push your-registry/geb-engine

# Deploy to your managed container platform
gcloud run deploy geb-engine \
  --image your-registry/geb-engine \
  --platform managed \
  --memory 8Gi \
  --cpu 4 \
  --allow-unauthenticated
```

> [!WARNING]
> **Disclaimer:** This is a personal development project. It is not an official product of Google, nor is it endorsed by or affiliated with Google in any way.
