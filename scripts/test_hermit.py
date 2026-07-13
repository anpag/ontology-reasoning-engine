import time
from owlready2 import *
import sys

def main(ontology_path):
    print('Loading Ontology into owlready2...')
    start_load = time.time()
    try:
        onto = get_ontology(f'file://{ontology_path}').load()
        print(f'Load Time: {time.time() - start_load:.2f}s')
    except Exception as e:
        print(f'Load FAILED: {e}')
        return

    print('Starting HermiT Reasoner (JVM)...')
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
