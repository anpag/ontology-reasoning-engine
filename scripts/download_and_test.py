import os
import sys
import time
import requests

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from core.loader import OntologyLoader
from core.reasoner import OntologyReasoner

def download_file(url, local_path):
    print(f"Downloading {url}...")
    with requests.get(url, stream=True) as r:
        r.raise_for_status()
        with open(local_path, 'wb') as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
    print(f"Downloaded to {local_path}")

def run_test(name, url, file_name):
    local_path = os.path.join(os.path.dirname(__file__), "..", "tests", file_name)
    if not os.path.exists(local_path):
        download_file(url, local_path)
        
    print(f"\n{'='*60}")
    print(f"Testing {name} Ontology")
    print(f"{'='*60}")
    
    loader = OntologyLoader()
    try:
        t0 = time.time()
        base_graph = loader.load_file(local_path)
        t1 = time.time()
        print(f"Loaded {len(base_graph)} triples in {t1-t0:.2f} seconds")
    except Exception as e:
        print(f"FAILED TO LOAD: {e}")
        return

    print("\n--- Running Custom C++ Engine ---")
    reasoner = OntologyReasoner(backend="custom")
    
    t0 = time.time()
    try:
        reasoned_graph = reasoner.materialize(base_graph)
        t1 = time.time()
        print(f"SUCCESS! Engine completed in {t1 - t0:.4f} seconds.")
        print(f"Total Triples after reasoning: {len(reasoned_graph)}")
        print(f"Inferred: {len(reasoned_graph) - len(base_graph)} new triples.")
    except Exception as e:
        print(f"CRASH DETECTED: {e}")

if __name__ == "__main__":
    # Test 1: ChEBI (Chemical Entities of Biological Interest) - MASSIVE OWL file
    run_test("ChEBI", "https://ftp.ebi.ac.uk/pub/databases/chebi/ontology/chebi.owl", "chebi.owl")
    
    # Test 2: QUDT Units (Metrology)
    run_test("QUDT Units", "https://qudt.org/2.1/vocab/unit", "qudt_unit.ttl")
