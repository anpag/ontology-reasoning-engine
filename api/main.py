import os
import tempfile
import subprocess
import logging
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(title="GEB: Graph Entailment Backplane")

# Allow local Angular app (localhost:4200) to hit the API over SSH proxy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # For dev over proxy
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)

class IngestResponse(BaseModel):
    status: str
    message: str
    job_id: str

def process_ontology_background(file_path: str, format: str, mode: str, out_nt: str):
    """
    Background task to process the ontology using the compiled Rust engine.
    """
    try:
        logging.info(f"Starting background processing for {file_path}")
        
        # 1. Run Native Rust Engine
        rust_binary = os.path.join(os.path.dirname(__file__), "..", "rust_engine", "target", "release", "geb_engine")
        
        if not os.path.exists(rust_binary):
            logging.error(f"Rust binary not found at {rust_binary}. Have you run `cargo build --release`?")
            return
            
        logging.info("Executing Rust Reasoner...")
        # Rust engine appends '.nt' internally to the prefix argument, so chop off '.nt' from out_nt prefix
        subprocess.run([rust_binary, format, mode, file_path, out_nt[:-3]], check=True)
        logging.info(f"Rust Reasoner completed. Output written to {out_nt}")
    except Exception as e:
        logging.error(f"Error during background processing: {e}")
    finally:
        # We intentionally keep the original uploaded file because the Rust reasoner
        # strips out literal annotations like rdfs:label. We need the original file 
        # to restore these labels during visualization.
        pass

@app.post("/ingest", response_model=IngestResponse)
async def ingest_ontology(
    background_tasks: BackgroundTasks,
    format: str = Form("xml"),
    mode: str = Form("w3c"),
    file: UploadFile = File(...)
):
    """
    Ingests an ontology file and schedules background reasoning (Rust).
    """
    if format not in ["xml", "turtle"]:
        return JSONResponse(status_code=400, content={"error": "format must be 'xml' or 'turtle'"})
    if mode not in ["w3c", "lpg"]:
        return JSONResponse(status_code=400, content={"error": "mode must be 'w3c' or 'lpg'"})

    # Save uploaded file to a temporary location
    fd, temp_path = tempfile.mkstemp(suffix=f".{format}")
    with os.fdopen(fd, "wb") as f:
        content = await file.read()
        f.write(content)

    logging.info(f"File {file.filename} uploaded and saved to {temp_path}")
    
    job_id = os.path.basename(temp_path)
    out_nt = os.path.join(tempfile.gettempdir(), f"{job_id}_out.nt")

    # Schedule the heavy processing in the background to prevent HTTP timeouts
    background_tasks.add_task(
        process_ontology_background,
        file_path=temp_path,
        format=format,
        mode=mode,
        out_nt=out_nt
    )

    return IngestResponse(
        status="accepted",
        message="Ontology received. Reasoning started in the background.",
        job_id=job_id
    )

@app.get("/ontologies")
def list_ontologies():
    """
    Lists all available ontologies that have been processed and cached.
    """
    import glob
    import os
    import time
    
    pattern = os.path.join(tempfile.gettempdir(), "*_out.nt")
    files = glob.glob(pattern)
    
    ontologies = []
    for f in files:
        basename = os.path.basename(f)
        job_id = basename.replace("_out.nt", "")
        stat = os.stat(f)
        size_mb = round(stat.st_size / (1024 * 1024), 2)
        created = time.ctime(stat.st_ctime)
        
        ontologies.append({
            "job_id": job_id,
            "name": job_id,
            "size_mb": size_mb,
            "created_at": created
        })
        
    # Sort by created desc
    ontologies.sort(key=lambda x: x["created_at"], reverse=True)
    return {"ontologies": ontologies}

@app.get("/result/{job_id}")
def get_result(job_id: str):
    """
    Retrieves the materialized N-Triples output graph.
    """
    # Security: prevent directory traversal
    if "/" in job_id or "\\" in job_id:
        raise HTTPException(status_code=400, detail="Invalid job ID")
        
    out_nt = os.path.join(tempfile.gettempdir(), f"{job_id}_out.nt")
    if not os.path.exists(out_nt):
        raise HTTPException(status_code=404, detail="Result not found or still processing.")
        
    return FileResponse(out_nt, media_type="application/n-triples", filename=f"{job_id}_reasoned.nt")

GRAPH_CACHE = {}

def get_cached_graph(job_id: str):
    if "/" in job_id or "\\" in job_id:
        raise HTTPException(status_code=400, detail="Invalid job ID")
        
    if job_id in GRAPH_CACHE:
        return GRAPH_CACHE[job_id]

    out_nt = os.path.join(tempfile.gettempdir(), f"{job_id}_out.nt")
    original_file = os.path.join(tempfile.gettempdir(), job_id)
    
    if not os.path.exists(out_nt):
        raise HTTPException(status_code=404, detail="Result not found or still processing.")
        
    from rdflib import Graph
    g = Graph()
    try:
        g.parse(out_nt, format="nt")
        
        # The inferred graph lacks labels, so we merge the original graph to recover them
        if os.path.exists(original_file):
            try:
                from rdflib.namespace import OWL
                fmt = "turtle" if original_file.endswith(".ttl") or original_file.endswith(".turtle") else "xml"
                g.parse(original_file, format=fmt)
                
                # Recursively follow owl:imports to get labels from imported modules (like in EMMO)
                imported_uris = set()
                def load_imports(graph):
                    new_imports = [str(o) for s, p, o in graph.triples((None, OWL.imports, None)) if str(o) not in imported_uris]
                    for uri in new_imports:
                        imported_uris.add(uri)
                        try:
                            logging.info(f"Following owl:imports -> {uri}")
                            # Most imported ontologies are available as turtle or xml via content negotiation
                            graph.parse(uri)
                            load_imports(graph)
                        except Exception as e:
                            logging.warning(f"Failed to follow import {uri}: {e}")
                            
                load_imports(g)
                logging.info(f"Successfully merged original graph {original_file} and its imports to recover labels.")
            except Exception as e:
                logging.error(f"Failed to parse original graph for labels: {e}")
                
    except Exception as e:
        logging.error(f"Error parsing graph: {e}")
        raise HTTPException(status_code=500, detail="Error parsing graph data.")
        
    GRAPH_CACHE[job_id] = g
    return g

def get_node_label(g, node):
    from rdflib.namespace import RDFS, SKOS
    for label in g.objects(node, SKOS.prefLabel):
        return str(label)
    for label in g.objects(node, RDFS.label):
        return str(label)
    c_id = str(node)
    return c_id.split("#")[-1] if "#" in c_id else c_id.split("/")[-1]

@app.get("/graph/{job_id}/roots")
def get_graph_roots(job_id: str):
    """
    Returns the top-level classes (nodes that are parents in subClassOf but never children).
    """
    g = get_cached_graph(job_id)
    from rdflib import URIRef
    from rdflib.namespace import RDFS
    
    roots = []
    parents = set(g.objects(predicate=RDFS.subClassOf))
    children = set(g.subjects(predicate=RDFS.subClassOf))
    
    true_roots = parents - children
    
    for c in true_roots:
        if isinstance(c, URIRef):
            c_id = str(c)
            name = get_node_label(g, c)
            roots.append({"data": {"id": c_id, "name": name, "type": "class", "uri": c_id}})
                
    return {"elements": roots}

@app.get("/graph/{job_id}/expand")
def get_graph_expand(job_id: str, node_uri: str):
    """
    Returns the 1-hop incoming and outgoing edges (and connected nodes) for the given URI in Cytoscape JSON format.
    """
    g = get_cached_graph(job_id)
    from rdflib import URIRef, BNode
    
    target_node = URIRef(node_uri)
    elements = []
    nodes = set()
    
    def add_node(n):
        n_id = str(n)
        if n_id not in nodes:
            nodes.add(n_id)
            name = get_node_label(g, n)
            elements.append({"data": {"id": n_id, "name": name, "type": "class", "uri": n_id}})
            
    # Always include the target node itself
    add_node(target_node)
    
    # Outgoing edges
    for p, o in g.predicate_objects(target_node):
        if isinstance(o, (URIRef, BNode)):
            add_node(o)
            edge_label = str(p).split("#")[-1] if "#" in str(p) else str(p).split("/")[-1]
            elements.append({"data": {"source": str(target_node), "target": str(o), "label": edge_label}})
            
    # Incoming edges
    for s, p in g.subject_predicates(target_node):
        if isinstance(s, (URIRef, BNode)):
            add_node(s)
            edge_label = str(p).split("#")[-1] if "#" in str(p) else str(p).split("/")[-1]
            elements.append({"data": {"source": str(s), "target": str(target_node), "label": edge_label}})
            
    return {"elements": elements}

@app.get("/graph/{job_id}/degree")
def get_graph_degree(job_id: str, node_uri: str):
    """
    Returns {"count": <integer>} representing the total number of incoming/outgoing edges for that URI.
    """
    g = get_cached_graph(job_id)
    from rdflib import URIRef, BNode
    
    target_node = URIRef(node_uri)
    count = 0
    
    # Outgoing
    for p, o in g.predicate_objects(target_node):
        if isinstance(o, (URIRef, BNode)):
            count += 1
            
    # Incoming
    for s, p in g.subject_predicates(target_node):
        if isinstance(s, (URIRef, BNode)):
            count += 1
            
    return {"count": count}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
