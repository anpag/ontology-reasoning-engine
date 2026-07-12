import os
import json
import argparse
import re
import io
from google.cloud import bigquery
from google.cloud.exceptions import NotFound

def upload_triples_to_bq(project_id, dataset_id, table_name, nt_file):
    client = bigquery.Client(project=project_id)
    dataset_ref = f"{project_id}.{dataset_id}"
    
    try:
        client.get_dataset(dataset_ref)
        print(f"Dataset {dataset_ref} found.")
    except NotFound:
        print(f"Creating dataset {dataset_ref}...")
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "US"
        client.create_dataset(dataset, timeout=30)
    
    table_id = f"{dataset_ref}.{table_name}"
    
    print(f"Parsing N-Triples from {nt_file}...")
    
    # Basic NTriples regex extractor
    triple_pattern = re.compile(r'^([^\s]+)\s+([^\s]+)\s+(.+)\s*\.\s*$')
    
    rows = []
    with open(nt_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            match = triple_pattern.match(line)
            if match:
                s, p, o = match.groups()
                # Clean up < > brackets if present for URIs
                rows.append({
                    "subject": s.strip("<>"),
                    "predicate": p.strip("<>"),
                    "object": o.strip()
                })
    
    if not rows:
        print("No valid triples found to upload.")
        return

    print(f"Parsed {len(rows)} triples. Starting BigQuery load job...")
    
    job_config = bigquery.LoadJobConfig(
        source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
        autodetect=True,
        write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
    )
    
    jsonl_data = "\n".join([json.dumps(row) for row in rows])
    
    file_obj = io.BytesIO(jsonl_data.encode('utf-8'))
    
    job = client.load_table_from_file(
        file_obj, 
        table_id, 
        job_config=job_config
    )
    job.result()  # Wait for the job to complete
    print(f"Success! Loaded {job.output_rows} rows into {table_id}.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Upload N-Triples to BigQuery")
    parser.add_argument("nt_file", help="Path to the N-Triples file")
    parser.add_argument("--project", default="brl-demos", help="GCP Project ID")
    parser.add_argument("--dataset", default="ontology_test", help="BQ Dataset ID")
    parser.add_argument("--table", default="raw_triples", help="BQ Table Name")
    args = parser.parse_args()
    
    upload_triples_to_bq(args.project, args.dataset, args.table, args.nt_file)
