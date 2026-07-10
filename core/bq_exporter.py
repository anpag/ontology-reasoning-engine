import os
import json
import logging
from typing import List, Dict
from google.cloud import bigquery
from rdflib import Graph
from google.cloud.exceptions import NotFound

logging.basicConfig(level=logging.INFO)

class BigQueryExporter:
    def __init__(self, project_id: str, dataset_id: str):
        self.project_id = project_id
        self.dataset_id = dataset_id
        # Initialize BQ Client
        self.client = bigquery.Client(project=project_id)
        self._ensure_dataset_exists()

    def _ensure_dataset_exists(self):
        dataset_ref = f"{self.project_id}.{self.dataset_id}"
        try:
            self.client.get_dataset(dataset_ref)
            logging.info(f"Dataset {dataset_ref} already exists.")
        except NotFound:
            dataset = bigquery.Dataset(dataset_ref)
            dataset.location = "US"
            self.client.create_dataset(dataset, timeout=30)
            logging.info(f"Created dataset {dataset_ref}.")

    def parse_and_extract(self, nt_file_path: str) -> Dict[str, List[Dict]]:
        """
        Parses the materialized N-Triples file using oxrdflib and runs SPARQL 
        to structure the graph into BigQuery schemas.
        """
        logging.info(f"Loading {nt_file_path} into memory for SPARQL extraction...")
        # Utilize the rust-backed oxrdflib for extreme performance
        g = Graph(store="Oxigraph")
        g.parse(nt_file_path, format="nt")
        logging.info(f"Graph loaded. Triples: {len(g)}")

        data = {
            "classes": self._extract_classes(g),
            "topology": self._extract_topology(g)
        }
        return data

    def _extract_classes(self, g: Graph) -> List[Dict]:
        """
        Extracts Class Dictionary (URIs, labels, definitions)
        """
        query = """
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        PREFIX owl: <http://www.w3.org/2002/07/owl#>
        PREFIX skos: <http://www.w3.org/2004/02/skos/core#>
        
        SELECT DISTINCT ?cls ?label ?definition
        WHERE {
            { ?cls a owl:Class } UNION { ?cls a rdfs:Class }
            OPTIONAL { 
                ?cls rdfs:label ?label .
                FILTER(lang(?label) = "" || lang(?label) = "en")
            }
            OPTIONAL { ?cls skos:definition ?definition }
            FILTER (isURI(?cls))
        }
        """
        results = g.query(query)
        rows = []
        for row in results:
            rows.append({
                "class_uri": str(row.cls),
                "label": str(row.label) if row.label else None,
                "definition": str(row.definition) if row.definition else None
            })
        logging.info(f"Extracted {len(rows)} class dictionary records.")
        return rows

    def _extract_topology(self, g: Graph) -> List[Dict]:
        """
        Extracts Topology Rules (Domain -> Property -> Range, SubClassOf)
        """
        query = """
        PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
        
        SELECT ?subject ?predicate ?object
        WHERE {
            ?subject ?predicate ?object .
            FILTER (?predicate IN (rdfs:subClassOf, rdfs:domain, rdfs:range))
            FILTER (isURI(?subject) && isURI(?object))
        }
        """
        results = g.query(query)
        rows = []
        for row in results:
            rows.append({
                "subject_uri": str(row.subject),
                "predicate_uri": str(row.predicate),
                "object_uri": str(row.object)
            })
        logging.info(f"Extracted {len(rows)} topology rules.")
        return rows

    def load_to_bigquery(self, table_name: str, rows: List[Dict]):
        if not rows:
            logging.warning(f"No rows to insert for {table_name}. Skipping.")
            return

        table_id = f"{self.project_id}.{self.dataset_id}.{table_name}"
        
        # LoadJobConfig handles auto-schema detection from JSON
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON,
            autodetect=True,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE
        )

        # Convert Dicts to JSONL in memory
        jsonl_data = "\n".join([json.dumps(row) for row in rows])
        
        logging.info(f"Starting BigQuery load job for {table_id}...")
        job = self.client.load_table_from_file(
            jsonl_data.encode('utf-8'), 
            table_id, 
            job_config=job_config
        )
        job.result()  # Wait for the job to complete
        logging.info(f"Loaded {job.output_rows} rows into {table_id}.")
