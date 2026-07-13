import os
import tempfile
import subprocess
import logging
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse, FileResponse
from pydantic import BaseModel

app = FastAPI(title="GEB: Graph Entailment Backplane")
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

@app.get("/health")
def health_check():
    return {"status": "healthy"}
