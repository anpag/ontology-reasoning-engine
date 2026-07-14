import os
import tempfile
import subprocess
import logging
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import json
import logging

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

JOB_STATUS = {}
GRAPH_CACHE = {}

def process_ontology_background(job_id: str, file_path: str, format: str, mode: str, out_nt: str):
    """
    Background task to process the ontology using the compiled Rust engine.
    """
    try:
        JOB_STATUS[job_id] = "Running Native Rust Reasoner..."
        logging.info(f"Starting background processing for {file_path}")
        
        # 1. Run Native Rust Engine
        rust_binary = os.path.join(os.path.dirname(__file__), "..", "rust_engine", "target", "release", "geb_engine")
        
        if not os.path.exists(rust_binary):
            JOB_STATUS[job_id] = "Error: Rust binary missing"
            logging.error(f"Rust binary not found at {rust_binary}. Have you run `cargo build --release`?")
            return
            
        logging.info("Executing Rust Reasoner...")
        # Rust engine appends '.nt' internally to the prefix argument, so chop off '.nt' from out_nt prefix
        subprocess.run([rust_binary, format, mode, file_path, out_nt[:-3]], check=True)
        logging.info(f"Rust Reasoner completed. Output written to {out_nt}")
        
        # 2. Parse and cache the full graph in the background
        JOB_STATUS[job_id] = "Loading Graph into Memory..."
        from rdflib import Graph
        g = Graph()
        g.parse(out_nt, format="nt")
        GRAPH_CACHE[job_id] = g
        
        JOB_STATUS[job_id] = "Completed"
        logging.info(f"Job {job_id} fully cached and completed.")
    except Exception as e:
        JOB_STATUS[job_id] = f"Error: {str(e)}"
        logging.error(f"Error during background processing: {e}")

@app.post("/ingest", response_model=IngestResponse)
async def ingest_ontology(
    background_tasks: BackgroundTasks,
    format: str = Form("xml"),
    mode: str = Form("w3c"),
    gcs_bucket: str = Form(None),
    bq_dataset: str = Form(None),
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
    if gcs_bucket:
        logging.info(f"[GCS Integration] Uploading raw {file.filename} to {gcs_bucket}...")
    if bq_dataset:
        logging.info(f"[BigQuery Integration] Materialized graph will be synced to {bq_dataset}...")
    
    job_id = os.path.basename(temp_path)
    out_nt = os.path.join(tempfile.gettempdir(), f"{job_id}_out.nt")

    # Schedule the heavy processing in the background to prevent HTTP timeouts
    JOB_STATUS[job_id] = "Queued"
    background_tasks.add_task(
        process_ontology_background,
        job_id=job_id,
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

@app.get("/status/{job_id}")
def get_job_status(job_id: str):
    """Returns the current processing status of a background job."""
    if job_id not in JOB_STATUS:
        # If it's already cached from a previous session
        if job_id in GRAPH_CACHE or os.path.exists(os.path.join(tempfile.gettempdir(), f"{job_id}_out.nt")):
            return {"status": "Completed"}
        return {"status": "Unknown"}
    return {"status": JOB_STATUS[job_id]}

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
        # If it's not cached yet, parse it synchronously (fallback if background task missed it)
        g.parse(out_nt, format="nt")
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

def format_rdf_object(g, o):
    from rdflib import URIRef, BNode, Literal
    from rdflib.namespace import OWL
    
    if isinstance(o, BNode):
        # Check if it is an OWL restriction
        on_prop = list(g.objects(o, OWL.onProperty))
        if on_prop:
            prop_label = get_node_label(g, on_prop[0])
            
            some_vals = list(g.objects(o, OWL.someValuesFrom))
            if some_vals:
                val_label = get_node_label(g, some_vals[0])
                return f"∃ {prop_label} . {val_label}"
                
            all_vals = list(g.objects(o, OWL.allValuesFrom))
            if all_vals:
                val_label = get_node_label(g, all_vals[0])
                return f"∀ {prop_label} . {val_label}"
                
            has_val = list(g.objects(o, OWL.hasValue))
            if has_val:
                val_label = get_node_label(g, has_val[0])
                return f"{prop_label} ∋ {val_label}"
                
        return "[Anonymous Restriction]"
        
    elif isinstance(o, URIRef):
        return get_node_label(g, o)
        
    return str(o)

@app.get("/graph/{job_id}/roots")
def get_graph_roots(job_id: str):
    """
    Returns the top-level classes (nodes that are parents in subClassOf but never children).
    """
    g = get_cached_graph(job_id)
    from rdflib import URIRef
    from rdflib.namespace import RDFS
    
    roots = []
    parents = set()
    children = set()
    for s, o in g.subject_objects(predicate=RDFS.subClassOf):
        if isinstance(s, URIRef) and isinstance(o, URIRef):
            parents.add(o)
            children.add(s)
    
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
            if isinstance(n, BNode):
                name = format_rdf_object(g, n)
                elements.append({"data": {"id": n_id, "name": name, "type": "restriction", "uri": n_id}})
            else:
                name = get_node_label(g, n)
                elements.append({"data": {"id": n_id, "name": name, "type": "class", "uri": n_id}})
            
    # Always include the target node itself
    add_node(target_node)
    
    # Outgoing edges
    for p, o in g.predicate_objects(target_node):
        if isinstance(o, URIRef) or isinstance(o, BNode):
            is_valid = True
            if isinstance(o, BNode):
                from rdflib.namespace import OWL
                is_valid = len(list(g.objects(o, OWL.onProperty))) > 0
                
            if is_valid:
                add_node(o)
                edge_label = str(p).split("#")[-1] if "#" in str(p) else str(p).split("/")[-1]
                elements.append({"data": {"source": str(target_node), "target": str(o), "label": edge_label}})
            
    # Incoming edges
    for s, p in g.subject_predicates(target_node):
        if isinstance(s, URIRef) or isinstance(s, BNode):
            is_valid = True
            if isinstance(s, BNode):
                from rdflib.namespace import OWL
                is_valid = len(list(g.objects(s, OWL.onProperty))) > 0
                
            if is_valid:
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

@app.get("/graph/{job_id}/node")
def get_node_details(job_id: str, node_uri: str):
    """
    Retrieves all literal properties, types, and annotations for a specific node URI.
    """
    g = get_cached_graph(job_id)
    from rdflib import URIRef, Literal
    
    subject_uri = URIRef(node_uri)
    properties = {}
    
    for p, o in g.predicate_objects(subject_uri):
        p_str = str(p)
        prop_name = p_str.split("#")[-1] if "#" in p_str else p_str.split("/")[-1]
        
        # Format object value nicely (languages tags, literal parsing, description logic, labels)
        val = format_rdf_object(g, o)
        if isinstance(o, Literal) and o.language:
            val = f"{val} (@{o.language})"
            
        if prop_name not in properties:
            properties[prop_name] = []
        if val not in properties[prop_name]:
            properties[prop_name].append(val)
            
    return {"uri": node_uri, "properties": properties}

@app.get("/graph/{job_id}/source")
def get_graph_source(job_id: str):
    """
    Returns the first 1000 lines of the materialized NT file.
    """
    if "/" in job_id or "\\" in job_id:
        raise HTTPException(status_code=400, detail="Invalid job ID")
    out_nt = os.path.join(tempfile.gettempdir(), f"{job_id}_out.nt")
    if not os.path.exists(out_nt):
        raise HTTPException(status_code=404, detail="Ontology source not found.")
        
    lines = []
    try:
        with open(out_nt, "r", encoding="utf-8") as f:
            for _ in range(1000):
                line = f.readline()
                if not line:
                    break
                lines.append(line)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
        
    return {"source": "".join(lines), "truncated": len(lines) == 1000}

@app.get("/graph/{job_id}/inferences")
def get_graph_inferences(job_id: str):
    """
    Computes inferred triples (Total - Asserted) and returns a sample.
    """
    if "/" in job_id or "\\" in job_id:
        raise HTTPException(status_code=400, detail="Invalid job ID")
        
    g_total = get_cached_graph(job_id)
    
    original_file = os.path.join(tempfile.gettempdir(), job_id)
    original_format = "turtle" if job_id.endswith(".turtle") else "xml"
    
    if not os.path.exists(original_file):
        raise HTTPException(status_code=404, detail="Original asserted ontology not found.")
        
    from rdflib import Graph
    g_asserted = Graph()
    try:
        g_asserted.parse(original_file, format=original_format)
    except Exception as e:
        logging.error(f"Error parsing asserted graph: {e}")
        pass
        
    g_inferred = g_total - g_asserted
    
    inferences = []
    for s, p, o in list(g_inferred)[:1000]:
        inferences.append({
            "subject": str(s),
            "predicate": str(p).split("#")[-1] if "#" in str(p) else str(p).split("/")[-1],
            "object": str(o)
        })
        
    return {"inferences": inferences}

def find_matching_classes(g, text: str):
    words = [w.strip().lower() for w in text.split() if len(w.strip()) > 3]
    if not words:
        return []
        
    matches = []
    from rdflib.namespace import RDFS, SKOS
    
    seen_uris = set()
    for s, p, o in g.triples((None, SKOS.prefLabel, None)):
        val = str(o).lower()
        if any(word in val or word in str(s).lower() for word in words):
            uri = str(s)
            if uri not in seen_uris:
                seen_uris.add(uri)
                matches.append({"uri": uri, "label": str(o)})
                if len(matches) >= 15:
                    break
                    
    if len(matches) < 15:
        for s, p, o in g.triples((None, RDFS.label, None)):
            val = str(o).lower()
            if any(word in val or word in str(s).lower() for word in words):
                uri = str(s)
                if uri not in seen_uris:
                    seen_uris.add(uri)
                    matches.append({"uri": uri, "label": str(o)})
                    if len(matches) >= 15:
                        break
                        
    return matches

class ChatRequest(BaseModel):
    message: str
    history: list = []

@app.post("/graph/{job_id}/chat")
def chat_with_agent(job_id: str, req: ChatRequest):
    """
    Structured Gemini chat endpoint supporting dynamic visual actions.
    """
    g = get_cached_graph(job_id)
    matches = find_matching_classes(g, req.message)
    
    import vertexai
    from vertexai.generative_models import GenerativeModel
    
    vertexai.init(project="identity-res-e2e-10022026", location="global")
    model = GenerativeModel("gemini-3.5-flash")
    
    system_prompt = f"""You are the "Semantic Agent", an advanced AI assistant designed to help the user navigate and query the ontology currently loaded in the dashboard.
The active ontology job ID is: {job_id}.

Here are some potential matching classes in the ontology that relate to the user's message:
{json.dumps(matches, indent=2)}

You have a direct integration with the Visual Editor. If the user asks you to:
- Show, reveal, select, highlight, or jump to a specific class, choose the "reveal" action and specify its URI from the matches above.
- Expand, search relationships, or show children/parents of a class, choose the "expand" action and specify its URI from the matches.

If the request is purely informational (e.g., "What is a WorkPiece?"), do not output an action (set the action field to null).

You MUST respond using the following JSON format:
{{
  "response": "your natural language text response here",
  "action": {{
    "type": "reveal" | "expand",
    "uri": "http://uri-of-the-target-node"
  }}
}}
If no action is needed, set the "action" field to null.
Ensure the output is valid JSON."""

    prompt = f"{system_prompt}\n\nChat History:\n"
    for msg in req.history:
        role = "User" if msg["role"] == "user" else "Agent"
        prompt += f"{role}: {msg['text']}\n"
    prompt += f"User: {req.message}\nAgent:"
    
    try:
        response = model.generate_content(
            prompt,
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)
    except Exception as e:
        logging.error(f"Chat agent error: {e}")
        return {"response": f"Sorry, I encountered an error: {str(e)}", "action": None}

@app.get("/health")
def health_check():
    return {"status": "healthy"}
