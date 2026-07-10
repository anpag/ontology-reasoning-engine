import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from core.loader import OntologyLoader
from core.reasoner import OntologyReasoner
from rdflib import Graph

def run_benchmark(file_path):
    print(f"\n{'='*60}")
    print(f"Benchmarking File: {os.path.basename(file_path)}")
    print(f"{'='*60}")
    
    loader = OntologyLoader()
    try:
        base_graph = loader.load_file(file_path)
    except Exception as e:
        print(f"Failed to load {file_path}: {e}")
        return
        
    initial_triples = len(base_graph)
    print(f"Initial Triples: {initial_triples}")
    
    # 1. Test Custom C++ Engine
    print("\n--- Testing Custom C++ Engine (Transitive Closure Only) ---")
    reasoner_custom = OntologyReasoner(backend="custom")
    t0 = time.time()
    try:
        # We pass a copy to avoid mutating the base graph directly before HermiT runs
        custom_graph = Graph()
        for t in base_graph:
            custom_graph.add(t)
            
        custom_reasoned = reasoner_custom.materialize(custom_graph)
        t1 = time.time()
        custom_triples = len(custom_reasoned)
        print(f"Time Taken: {t1 - t0:.2f} seconds")
        print(f"Inferred Triples: {custom_triples - initial_triples}")
    except Exception as e:
        print(f"Custom Engine Failed: {e}")
        custom_triples = initial_triples

    # 2. Test HermiT (Full OWL 2 DL)
    print("\n--- Testing HermiT (Full OWL 2 DL) ---")
    reasoner_hermit = OntologyReasoner(backend="hermit")
    t0 = time.time()
    try:
        hermit_graph = Graph()
        for t in base_graph:
            hermit_graph.add(t)
            
        hermit_reasoned = reasoner_hermit.materialize(hermit_graph)
        t1 = time.time()
        hermit_triples = len(hermit_reasoned)
        print(f"Time Taken: {t1 - t0:.2f} seconds")
        print(f"Inferred Triples: {hermit_triples - initial_triples}")
    except Exception as e:
        print(f"HermiT Failed: {e}")
        hermit_triples = initial_triples
        
    # Analysis
    print("\n--- Analysis ---")
    missed_triples = hermit_triples - custom_triples
    if missed_triples > 0:
        print(f"The Custom C++ Engine missed {missed_triples} complex relationships that HermiT found.")
    elif missed_triples < 0:
        print("The Custom Engine found MORE triples than HermiT (likely due to differing rule implementations).")
    else:
        print("Both engines found the exact same number of relationships! (100% Completeness)")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python compare_engines.py <emmo.ttl> <obi.owl>")
        sys.exit(1)
        
    emmo_path = sys.argv[1]
    obi_path = sys.argv[2]
    
    if os.path.exists(emmo_path):
        run_benchmark(emmo_path)
    if os.path.exists(obi_path):
        run_benchmark(obi_path)
