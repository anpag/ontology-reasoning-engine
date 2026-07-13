import os
import sys

def build_lpg_test():
    content = """@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix ex: <http://example.org/> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

# The reification of an observation triple (N-ary relation)
ex:stmt1 a rdf:Statement ;
    rdf:subject ex:ExperimentA ;
    rdf:predicate ex:hasTemperature ;
    rdf:object "100"^^xsd:integer ;
    ex:unit "Celsius" ;
    ex:confidence "0.99"^^xsd:float ;
    ex:recordedBy ex:ScientistBob .
"""
    out_path = sys.argv[1]
    with open(out_path, "w") as f:
        f.write(content)
    print(f"Test data written to {out_path}")

if __name__ == "__main__":
    build_lpg_test()
