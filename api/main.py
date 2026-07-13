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

def process_ontology_background(file_path: str, format: str, out_nt: str):
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
        subprocess.run([rust_binary, format, file_path, out_nt], check=True)
        logging.info(f"Rust Reasoner completed. Output written to {out_nt}")
    except Exception as e:
        logging.error(f"Error during background processing: {e}")
    finally:
        # Cleanup uploaded file, keep the out_nt for the client to download
        if os.path.exists(file_path):
            os.remove(file_path)

@app.post("/ingest", response_model=IngestResponse)
async def ingest_ontology(
    background_tasks: BackgroundTasks,
    format: str = Form("xml"),
    file: UploadFile = File(...)
):
    """
    Ingests an ontology file and schedules background reasoning (Rust).
    """
    if format not in ["xml", "turtle"]:
        return JSONResponse(status_code=400, content={"error": "format must be 'xml' or 'turtle'"})

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
        out_nt=out_nt
    )

    return IngestResponse(
        status="accepted",
        message="Ontology received. Reasoning started in the background.",
        job_id=job_id
    )

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

@app.get("/graph/{job_id}")
def get_graph(job_id: str):
    """
    Parses the output N-Triples graph and returns Cytoscape-compatible JSON.
    """
    if "/" in job_id or "\\" in job_id:
        raise HTTPException(status_code=400, detail="Invalid job ID")
        
    out_nt = os.path.join(tempfile.gettempdir(), f"{job_id}_out.nt")
    if not os.path.exists(out_nt):
        raise HTTPException(status_code=404, detail="Result not found or still processing.")
        
    try:
        from rdflib import Graph, URIRef, BNode, Literal
        g = Graph()
        g.parse(out_nt, format="nt")
        
        elements = []
        nodes = set()
        
        # Build Cytoscape JSON
        for s, p, o in g:
            # Source Node
            s_id = str(s)
            if s_id not in nodes:
                nodes.add(s_id)
                name = s_id.split("#")[-1] if "#" in s_id else s_id.split("/")[-1]
                elements.append({"data": {"id": s_id, "name": name, "type": "class", "uri": s_id}})
            
            # Target Node (only add edge if object is another node, ignore literals for graph structure)
            if isinstance(o, (URIRef, BNode)):
                o_id = str(o)
                if o_id not in nodes:
                    nodes.add(o_id)
                    name = o_id.split("#")[-1] if "#" in o_id else o_id.split("/")[-1]
                    elements.append({"data": {"id": o_id, "name": name, "type": "class", "uri": o_id}})
                
                # Edge
                edge_label = str(p).split("#")[-1] if "#" in str(p) else str(p).split("/")[-1]
                elements.append({"data": {"source": s_id, "target": o_id, "label": edge_label}})
                
        return {"elements": elements}
    except Exception as e:
        logging.error(f"Error parsing graph: {e}")
        raise HTTPException(status_code=500, detail="Error generating graph data.")

@app.get("/health")
def health_check():
    return {"status": "healthy"}
