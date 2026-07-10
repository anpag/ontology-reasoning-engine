import time
import sys

def test_rdflib(file_path, fmt):
    import rdflib
    print("\n--- Testing RDFLib (Python baseline) ---")
    g = rdflib.Graph()
    t0 = time.time()
    g.parse(file_path, format=fmt)
    t1 = time.time()
    print(f"RDFLib parsed {len(g)} triples in {t1-t0:.2f} seconds.")

def test_pyoxigraph(file_path, fmt):
    import pyoxigraph
    print("\n--- Testing Pyoxigraph (Rust Native via Python) ---")
    store = pyoxigraph.Store()
    
    if fmt == "xml":
        mimetype = "application/rdf+xml"
    else:
        mimetype = "text/turtle"
        
    t0 = time.time()
    with open(file_path, "rb") as f:
        store.load(f, mimetype)
    t1 = time.time()
    print(f"Pyoxigraph parsed triples in {t1-t0:.2f} seconds.")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python benchmark_parsers.py <file> <format: xml|turtle>")
        sys.exit(1)
        
    file_path = sys.argv[1]
    fmt = sys.argv[2]
    
    test_pyoxigraph(file_path, fmt)
    test_rdflib(file_path, fmt)
