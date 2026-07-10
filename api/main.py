import os
import tempfile
import subprocess
import logging
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from core.bq_exporter import BigQueryExporter

app = FastAPI(title="Ontology Reasoning Engine")
logging.basicConfig(level=logging.INFO)

class IngestResponse(BaseModel):
    status: str
    message: str
    job_id: str

def process_ontology_background(file_path: str, format: str, project_id: str, dataset_id: str):
    """
    Background task to process the ontology using the compiled Rust engine 
    and export the materialization to BigQuery.
    """
    try:
        logging.info(f"Starting background processing for {file_path}")
        out_nt = f"{file_path}_out.nt"
        
        # 1. Run Native Rust Engine
        rust_binary = os.path.join(os.path.dirname(__file__), "..", "rust_engine", "target", "release", "custom_reasoner_rust")
        
        if not os.path.exists(rust_binary):
            logging.error(f"Rust binary not found at {rust_binary}. Have you run `cargo build --release`?")
            return
            
        logging.info("Executing Rust Reasoner...")
        subprocess.run([rust_binary, format, file_path, out_nt], check=True)
        logging.info(f"Rust Reasoner completed. Output written to {out_nt}")
        
        # 2. Extract and Load to BigQuery
        exporter = BigQueryExporter(project_id, dataset_id)
        data = exporter.parse_and_extract(out_nt)
        
        exporter.load_to_bigquery("ontology_classes", data["classes"])
        exporter.load_to_bigquery("ontology_topology", data["topology"])
        
        logging.info("BigQuery export complete.")
    except Exception as e:
        logging.error(f"Error during background processing: {e}")
    finally:
        # Cleanup temp files
        if os.path.exists(file_path):
            os.remove(file_path)
        if os.path.exists(out_nt):
            os.remove(out_nt)

@app.post("/ingest", response_model=IngestResponse)
async def ingest_ontology(
    background_tasks: BackgroundTasks,
    project_id: str = Form(...),
    dataset_id: str = Form(...),
    format: str = Form("xml"), # "xml" or "turtle"
    file: UploadFile = File(...)
):
    """
    Ingests an ontology file, schedules background reasoning (Rust), 
    and exports the materialized graph to BigQuery.
    """
    if format not in ["xml", "turtle"]:
        return JSONResponse(status_code=400, content={"error": "format must be 'xml' or 'turtle'"})

    # Save uploaded file to a temporary location
    fd, temp_path = tempfile.mkstemp(suffix=f".{format}")
    with os.fdopen(fd, "wb") as f:
        content = await file.read()
        f.write(content)

    logging.info(f"File {file.filename} uploaded and saved to {temp_path}")

    # Schedule the heavy processing in the background to prevent HTTP timeouts
    background_tasks.add_task(
        process_ontology_background,
        file_path=temp_path,
        format=format,
        project_id=project_id,
        dataset_id=dataset_id
    )

    return IngestResponse(
        status="accepted",
        message="Ontology received. Reasoning and BigQuery export started in the background.",
        job_id=temp_path
    )

@app.get("/health")
def health_check():
    return {"status": "healthy"}
