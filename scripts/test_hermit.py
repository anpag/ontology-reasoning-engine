import time
import sys
from owlready2 import *
import owlready2.reasoning

# Allocate 32GB of RAM to the JVM to prevent OutOfMemoryError on massive ontologies like NCIT
owlready2.reasoning.JAVA_MEMORY = 32000

def main(ontology_path):
    print(f'Loading Ontology ({ontology_path}) into owlready2...')
    start_load = time.time()
    try:
        onto = get_ontology(f'file://{ontology_path}').load()
        print(f'Load Time: {time.time() - start_load:.2f}s')
    except Exception as e:
        print(f'Load FAILED: {e}')
        return

    print('Starting HermiT Reasoner (JVM allocated 32GB RAM)...')
    start_reason = time.time()
    try:
        with onto:
            sync_reasoner(debug=0)
        print(f'HermiT Reasoning Time: {time.time() - start_reason:.2f}s')
        print(f'Total Time: {time.time() - start_load:.2f}s')
    except Exception as e:
        print(f'HermiT FAILED: {e}')

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 test_hermit.py <path_to_ontology>")
        sys.exit(1)
    main(sys.argv[1])
