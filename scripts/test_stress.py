import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from core.loader import OntologyLoader
from core.reasoner import OntologyReasoner

def run_stress_test():
    file_path = os.path.join(os.path.dirname(__file__), "..", "tests", "stress_test.ttl")
    
    print(f"Loading Malicious Ontology: {file_path}")
    loader = OntologyLoader()
    try:
        base_graph = loader.load_file(file_path)
    except Exception as e:
        print(f"FAILED TO LOAD: {e}")
        return
        
    print(f"Initial Triples: {len(base_graph)}")
    
    print("\n--- Running Custom C++ Engine (Testing for Infinite Loops) ---")
    reasoner = OntologyReasoner(backend="custom")
    
    t0 = time.time()
    try:
        reasoned_graph = reasoner.materialize(base_graph)
        t1 = time.time()
        print(f"SUCCESS! Engine completed in {t1 - t0:.4f} seconds without infinite looping.")
        print(f"Total Triples after reasoning: {len(reasoned_graph)}")
        
        # Verify the circular loop A -> A exists
        subclass_uri = "http://www.w3.org/2000/01/rdf-schema#subClassOf"
        class_a = "http://example.org/ClassA"
        
        found_loop = False
        for s, p, o in reasoned_graph:
            if str(s) == class_a and str(p) == subclass_uri and str(o) == class_a:
                found_loop = True
                
        if found_loop:
            print("Successfully resolved circular reference (ClassA subClassOf ClassA) without crashing.")
            
    except Exception as e:
        print(f"CRASH DETECTED: {e}")

if __name__ == "__main__":
    run_stress_test()
